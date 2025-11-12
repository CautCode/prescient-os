"""
Portfolio Orchestrator - Lightweight coordinator for portfolio trading cycles

This orchestrator is responsible for:
1. Mapping portfolios to their strategy controllers
2. Coordinating the trading cycle workflow
3. Executing signals via paper trading controller
4. Creating portfolio snapshots
5. Handling errors and logging

What this orchestrator does NOT do:
- Does NOT know about filtering parameters (that's the strategy's job)
- Does NOT call events/markets controllers directly
- Does NOT know about strategy-specific logic

Port: 8004
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, List, Optional
import requests
import os
from datetime import datetime
import logging

# Set up logging
log_level = getattr(logging, os.getenv('PYTHON_LOG_LEVEL', 'INFO'))
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Portfolio Orchestrator", version="1.0.0")

# Strategy controller mapping - maps strategy_type to controller port
STRATEGY_CONTROLLER_PORTS = {
    'momentum': 8002,
    'mean_reversion': 8005,
    'arbitrage': 8006,
    'hybrid': 8007
}

# Controller URLs
PAPER_TRADING_API_BASE = "http://localhost:8003"

# DB operations (for history snapshots)
from src.db.operations import (
    insert_portfolio_history_snapshot,
    get_portfolio_state,
    get_all_portfolios
)


def get_strategy_controller_url(strategy_type: str) -> str:
    """
    Map strategy type to controller URL

    Args:
        strategy_type: Strategy type (e.g., 'momentum', 'mean_reversion')

    Returns:
        Full URL for the strategy controller

    Raises:
        ValueError: If strategy type is unknown
    """
    port = STRATEGY_CONTROLLER_PORTS.get(strategy_type)
    if not port:
        raise ValueError(
            f"Unknown strategy type: '{strategy_type}'. "
            f"Available strategies: {list(STRATEGY_CONTROLLER_PORTS.keys())}"
        )
    return f"http://localhost:{port}"


def create_daily_portfolio_snapshot(portfolio_data: Dict, portfolio_id: int):
    """
    Create daily portfolio snapshot in database

    Args:
        portfolio_data: Portfolio data dictionary
        portfolio_id: Portfolio ID
    """
    try:
        now = datetime.now()
        open_positions = len([
            p for p in portfolio_data.get('positions', [])
            if p.get('status') == 'open'
        ])

        snapshot = {
            'portfolio_id': portfolio_id,
            'snapshot_date': now.date(),
            'timestamp': now,
            'balance': portfolio_data.get('current_balance', 0),
            'total_invested': portfolio_data.get('total_invested', 0),
            'total_profit_loss': portfolio_data.get('total_profit_loss', 0),
            'total_value': (
                portfolio_data.get('current_balance', 0) +
                portfolio_data.get('total_profit_loss', 0)
            ),
            'open_positions': open_positions,
            'trade_count': portfolio_data.get('trade_count', 0)
        }

        snapshot_id = insert_portfolio_history_snapshot(snapshot)
        logger.info(
            f"Created snapshot for portfolio {portfolio_id}: "
            f"id={snapshot_id}, value=${snapshot['total_value']:.2f}"
        )
    except Exception as e:
        logger.error(f"Error creating portfolio snapshot: {e}")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Portfolio Orchestrator is running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/orchestrator/run-portfolio-cycle")
async def run_portfolio_cycle(portfolio_id: int):
    """
    Run complete trading cycle for a single portfolio

    This is the simplified orchestrator workflow:
    1. Get portfolio info (loads strategy_type)
    2. Route to appropriate strategy controller
    3. Strategy controller handles ALL filtering and signal generation
    4. Execute signals via paper trading controller
    5. Update prices
    6. Create portfolio snapshot

    Args:
        portfolio_id: Portfolio ID to run cycle for

    Returns:
        Complete cycle results including strategy and execution details
    """
    try:
        logger.info(f"=== ORCHESTRATOR: Starting cycle for portfolio {portfolio_id} ===")

        # Step 1: Get portfolio and determine strategy
        logger.info("Step 1: Loading portfolio configuration...")
        try:
            portfolio = get_portfolio_state(portfolio_id)
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))

        strategy_type = portfolio['strategy_type']
        portfolio_name = portfolio['name']

        # Verify portfolio is active
        if portfolio['status'] != 'active':
            raise HTTPException(
                status_code=400,
                detail=f"Portfolio {portfolio_id} is {portfolio['status']}, not active"
            )

        logger.info(f"Portfolio: {portfolio_name} | Strategy: {strategy_type}")

        # Step 2: Get strategy controller URL
        try:
            strategy_url = get_strategy_controller_url(strategy_type)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        # Step 3: Call strategy controller to execute full cycle
        # The strategy controller handles ALL filtering and signal generation
        logger.info(f"Step 2: Calling {strategy_type} strategy controller...")
        try:
            strategy_response = requests.post(
                f"{strategy_url}/strategy/execute-full-cycle",
                params={"portfolio_id": portfolio_id},
                timeout=300
            )
            strategy_response.raise_for_status()
            strategy_result = strategy_response.json()

            signals_generated = strategy_result.get('signals_generated', 0)
            logger.info(f"✓ Strategy generated {signals_generated} signals")
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Error calling strategy controller: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Strategy controller error: {str(e)}"
            )

        # Step 4: Execute signals via paper trading controller
        logger.info("Step 3: Executing signals...")
        try:
            execute_response = requests.get(
                f"{PAPER_TRADING_API_BASE}/paper-trading/execute-signals",
                params={"portfolio_id": portfolio_id},
                timeout=300
            )
            execute_response.raise_for_status()
            execute_result = execute_response.json()

            trades_executed = execute_result.get('execution_summary', {}).get('executed_trades', 0)
            logger.info(f"✓ Executed {trades_executed} trades")
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ Error executing signals: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Trade execution error: {str(e)}"
            )

        # Step 5: Update prices for this portfolio
        logger.info("Step 4: Updating prices...")
        try:
            price_response = requests.get(
                f"{PAPER_TRADING_API_BASE}/price-updater/update",
                params={"portfolio_id": portfolio_id},
                timeout=60
            )
            if price_response.status_code == 200:
                logger.info("✓ Prices updated")
            else:
                logger.warning(f"Price update returned status {price_response.status_code}")
        except Exception as price_error:
            # Don't fail the whole cycle if price update fails
            logger.warning(f"Price update failed (non-critical): {price_error}")

        # Step 6: Create portfolio snapshot
        logger.info("Step 5: Creating portfolio snapshot...")
        try:
            portfolio_response = requests.get(
                f"{PAPER_TRADING_API_BASE}/portfolios/{portfolio_id}",
                timeout=60
            )
            portfolio_response.raise_for_status()
            portfolio_data = portfolio_response.json().get('portfolio', {})

            create_daily_portfolio_snapshot(portfolio_data, portfolio_id)
            logger.info("✓ Portfolio snapshot created")
        except Exception as snapshot_error:
            # Don't fail the whole cycle if snapshot fails
            logger.warning(f"Snapshot creation failed (non-critical): {snapshot_error}")

        logger.info(f"=== ORCHESTRATOR: Completed cycle for portfolio {portfolio_id} ===")

        return {
            "message": f"Portfolio cycle completed for {portfolio_name}",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio_name,
            "strategy_type": strategy_type,
            "strategy_result": strategy_result,
            "execution_result": execute_result,
            "summary": {
                "signals_generated": signals_generated,
                "trades_executed": trades_executed,
                "cycle_completed": True
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in portfolio cycle: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/orchestrator/run-all-portfolios")
async def run_all_portfolios():
    """
    Run trading cycle for all active portfolios

    This endpoint iterates through all active portfolios and runs
    the portfolio cycle for each one using run_portfolio_cycle.

    Returns:
        Aggregated results for all portfolio cycles
    """
    try:
        logger.info("=== ORCHESTRATOR: Starting cycle for all active portfolios ===")

        # Get all active portfolios
        portfolios = get_all_portfolios(status='active')
        logger.info(f"Found {len(portfolios)} active portfolios")

        if not portfolios:
            raise HTTPException(status_code=404, detail="No active portfolios found")

        results = []
        successful = 0
        failed = 0

        # Run cycle for each portfolio
        for portfolio in portfolios:
            portfolio_id = portfolio['portfolio_id']
            portfolio_name = portfolio['name']

            try:
                logger.info(f"Processing portfolio {portfolio_id}: {portfolio_name}")

                # Call run_portfolio_cycle for this portfolio
                result = await run_portfolio_cycle(portfolio_id)

                results.append({
                    "portfolio_id": portfolio_id,
                    "portfolio_name": portfolio_name,
                    "status": "success",
                    "result": result
                })
                successful += 1

                logger.info(f"✓ Completed portfolio {portfolio_id}")

            except Exception as portfolio_error:
                logger.error(f"✗ Error in portfolio {portfolio_id}: {portfolio_error}")
                results.append({
                    "portfolio_id": portfolio_id,
                    "portfolio_name": portfolio_name,
                    "status": "error",
                    "error": str(portfolio_error)
                })
                failed += 1

        logger.info(
            f"=== ORCHESTRATOR: Completed all portfolios "
            f"({successful} success, {failed} failed) ==="
        )

        return {
            "message": f"Completed cycles for {len(portfolios)} portfolios",
            "summary": {
                "total_portfolios": len(portfolios),
                "successful": successful,
                "failed": failed,
                "overall_success": failed == 0
            },
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in run_all_portfolios: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/orchestrator/status")
async def get_orchestrator_status():
    """
    Get status of orchestrator and all strategy controllers

    This endpoint checks the health of:
    - All configured strategy controllers
    - Paper trading controller
    - Number of active portfolios

    Returns:
        Status information for all components
    """
    try:
        status = {
            "timestamp": datetime.now().isoformat(),
            "orchestrator": "online",
            "version": "1.0.0",
            "strategy_controllers": {},
            "paper_trading_controller": {},
            "portfolios": {}
        }

        # Check each strategy controller
        for strategy_type, port in STRATEGY_CONTROLLER_PORTS.items():
            try:
                url = f"http://localhost:{port}/strategy/info"
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                status["strategy_controllers"][strategy_type] = {
                    "status": "online",
                    "port": port,
                    "info": response.json()
                }
            except Exception as e:
                status["strategy_controllers"][strategy_type] = {
                    "status": "offline",
                    "port": port,
                    "error": str(e)
                }

        # Check paper trading controller
        try:
            response = requests.get(f"{PAPER_TRADING_API_BASE}/paper-trading/status", timeout=5)
            response.raise_for_status()
            status["paper_trading_controller"] = {
                "status": "online",
                "url": PAPER_TRADING_API_BASE
            }
        except Exception as e:
            status["paper_trading_controller"] = {
                "status": "offline",
                "url": PAPER_TRADING_API_BASE,
                "error": str(e)
            }

        # Get portfolio counts
        try:
            all_portfolios = get_all_portfolios()
            active_portfolios = get_all_portfolios(status='active')
            status["portfolios"] = {
                "total": len(all_portfolios),
                "active": len(active_portfolios),
                "paused": len([p for p in all_portfolios if p['status'] == 'paused']),
                "archived": len([p for p in all_portfolios if p['status'] == 'archived'])
            }
        except Exception as e:
            status["portfolios"] = {
                "error": str(e)
            }

        # Determine overall health
        online_strategies = len([
            s for s in status["strategy_controllers"].values()
            if s["status"] == "online"
        ])
        total_strategies = len(STRATEGY_CONTROLLER_PORTS)

        if online_strategies == total_strategies and status["paper_trading_controller"]["status"] == "online":
            status["overall_health"] = "healthy"
        elif online_strategies > 0:
            status["overall_health"] = "degraded"
        else:
            status["overall_health"] = "unhealthy"

        return status

    except Exception as e:
        logger.error(f"Error getting orchestrator status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orchestrator/strategies")
async def list_available_strategies():
    """
    List all available trading strategies

    Returns:
        List of available strategies with their controller information
    """
    strategies = []

    for strategy_type, port in STRATEGY_CONTROLLER_PORTS.items():
        strategy_info = {
            "strategy_type": strategy_type,
            "port": port,
            "url": f"http://localhost:{port}",
            "status": "unknown"
        }

        try:
            response = requests.get(f"http://localhost:{port}/strategy/info", timeout=5)
            if response.status_code == 200:
                info = response.json()
                strategy_info["status"] = "online"
                strategy_info["name"] = info.get("name")
                strategy_info["description"] = info.get("description")
                strategy_info["version"] = info.get("version")
            else:
                strategy_info["status"] = "offline"
        except Exception:
            strategy_info["status"] = "offline"

        strategies.append(strategy_info)

    return {
        "message": "Available trading strategies",
        "total_strategies": len(strategies),
        "strategies": strategies,
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
    # uvicorn src.portfolio_orchestrator:app --reload --port 8004
