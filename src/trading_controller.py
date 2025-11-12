# Trading Controller - Orchestrates full trading cycle, coordinates all controllers, provides system status
# Main functions: run_full_trading_cycle(), get_trading_status(), get_performance_summary()
# Used by: Main entry point for automated trading operations, coordinates events->markets->strategy->execution (paper trading)

from fastapi import FastAPI, HTTPException
from typing import Dict, List, Optional
import requests
import json
import os
from datetime import datetime
import logging

# Set up logging
log_level = getattr(logging, os.getenv('PYTHON_LOG_LEVEL', 'INFO'))
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Polymarket Trading Controller API", version="1.0.0")

# Configuration
EVENTS_API_BASE = "http://localhost:8000"
MARKETS_API_BASE = "http://localhost:8001"
STRATEGY_API_BASE = "http://localhost:8002"
PAPER_TRADING_API_BASE = "http://localhost:8003"

# DB operations (Phase 2 - History)
from src.db.operations import (
    insert_portfolio_history_snapshot,
    insert_signal_archive,
    get_portfolio_history,
    get_trades,
)

def call_api(url: str, method: str = "GET", timeout: int = 300) -> Optional[Dict]:
    """
    Call API endpoint with error handling
    
    Args:
        url: API endpoint URL
        method: HTTP method
        timeout: Request timeout
        
    Returns:
        API response or None if error
    """
    try:
        logger.info(f"Calling API: {method} {url}")
        response = requests.request(method, url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API call failed: {method} {url} - {e}")
        return None

def ensure_data_directories():
    """
    Create necessary data directories if they don't exist
    """
    os.makedirs("data/history", exist_ok=True)

def create_daily_portfolio_snapshot(portfolio_data: Dict, portfolio_id: Optional[int] = None):
    """
    Create daily portfolio snapshot (DB-only, Phase 2).

    Args:
        portfolio_data: Portfolio data dictionary
        portfolio_id: Portfolio ID (optional, defaults to first active portfolio)
    """
    try:
        now = datetime.now()
        open_positions = len([p for p in portfolio_data.get('positions', []) if p.get('status') == 'open'])
        snapshot = {
            'snapshot_date': now.date(),
            'timestamp': now,
            'balance': portfolio_data.get('balance', 0),
            'total_invested': portfolio_data.get('total_invested', 0),
            'total_profit_loss': portfolio_data.get('total_profit_loss', 0),
            'total_value': portfolio_data.get('balance', 0) + portfolio_data.get('total_profit_loss', 0),
            'open_positions': open_positions,
            'trade_count': portfolio_data.get('trade_count', 0),
        }
        snapshot_id = insert_portfolio_history_snapshot(snapshot, portfolio_id=portfolio_id)
        logger.info(
            f"Inserted portfolio snapshot id={snapshot_id} total_value={snapshot['total_value']:.2f} portfolio_id={portfolio_id}"
        )
    except Exception as e:
        logger.error(f"Error creating portfolio snapshot (DB): {e}")

def archive_current_signals():
    """
    Archive current signals (DB-only, Phase 2).
    Reads current signals from existing JSON file if present and inserts into DB archive.
    """
    try:
        signals_path = os.path.join("data", "trades", "current_signals.json")
        if not os.path.exists(signals_path):
            return

        with open(signals_path, "r", encoding="utf-8") as f:
            signals = json.load(f)

        if not signals:
            return

        archived_at = datetime.now()
        archive_id = insert_signal_archive(archived_at, signals)
        logger.info(f"Archived {len(signals)} signals to DB (archive_id={archive_id})")
    except Exception as e:
        logger.error(f"Error archiving signals (DB): {e}")

# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Polymarket Trading Controller API is running", "timestamp": datetime.now().isoformat()}

@app.get("/trading/run-portfolio-cycle")
async def run_portfolio_trading_cycle(
    portfolio_id: int,
    # Event filtering parameters
    event_min_liquidity: float = 10000,
    event_min_volume: float = 50000,
    event_min_volume_24hr: Optional[float] = None,
    event_max_days_until_end: Optional[int] = None,
    event_min_days_until_end: Optional[int] = None,

    # Market filtering parameters
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    min_market_conviction: Optional[float] = 0.5,
    max_market_conviction: Optional[float] = 0.6
):
    """
    Run complete trading cycle for a specific portfolio

    Args:
        portfolio_id: Portfolio ID to run cycle for
        ... (same filtering parameters as full cycle)

    Returns:
        Trading cycle results for the specified portfolio
    """
    from src.db.operations import get_portfolio_state

    try:
        logger.info(f"=== STARTING PORTFOLIO TRADING CYCLE FOR PORTFOLIO {portfolio_id} ===")

        # Verify portfolio exists
        try:
            portfolio = get_portfolio_state(portfolio_id)
            logger.info(f"Running cycle for portfolio: {portfolio['name']} (ID: {portfolio_id})")
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))

        # Ensure directories exist
        ensure_data_directories()

        results = {
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "cycle_started": datetime.now().isoformat(),
            "steps": [],
            "success": True,
            "error_details": None
        }

        # Step 1: Fetch and filter markets (shared data)
        logger.info("Step 1: Fetching and filtering markets...")
        export_events_url = f"{EVENTS_API_BASE}/events/export-all-active-events-db"
        export_response = call_api(export_events_url)

        if export_response:
            results["steps"].append({
                "step": "1a",
                "name": "Export Events",
                "status": "completed",
                "message": f"Exported {export_response.get('total_events', 0)} events"
            })
        else:
            raise HTTPException(status_code=500, detail="Event export failed")

        # Filter events
        filter_events_url = f"{EVENTS_API_BASE}/events/filter-trading-candidates-db"
        event_params = {
            "min_liquidity": event_min_liquidity,
            "min_volume": event_min_volume,
            "min_volume_24hr": event_min_volume_24hr,
            "max_days_until_end": event_max_days_until_end,
            "min_days_until_end": event_min_days_until_end
        }
        event_param_string = "&".join([f"{k}={v}" for k, v in event_params.items() if v is not None])
        filter_response = call_api(f"{filter_events_url}?{event_param_string}")

        if filter_response:
            results["steps"].append({
                "step": "1b",
                "name": "Filter Events",
                "status": "completed",
                "message": f"Filtered {filter_response.get('total_candidates', 0)} candidates"
            })
        else:
            raise HTTPException(status_code=500, detail="Event filtering failed")

        # Filter markets
        markets_url = f"{MARKETS_API_BASE}/markets/export-filtered-markets-db"
        market_params = {
            "min_liquidity": min_liquidity,
            "min_volume": min_volume,
            "min_volume_24hr": min_volume_24hr,
            "min_market_conviction": min_market_conviction,
            "max_market_conviction": max_market_conviction
        }
        market_param_string = "&".join([f"{k}={v}" for k, v in market_params.items() if v is not None])
        markets_response = call_api(f"{markets_url}?{market_param_string}")

        if markets_response:
            results["steps"].append({
                "step": "1c",
                "name": "Filter Markets",
                "status": "completed",
                "message": f"Filtered {markets_response.get('filtered_markets', 0)} markets"
            })
        else:
            raise HTTPException(status_code=500, detail="Market filtering failed")

        # Step 2: Generate signals for this portfolio
        logger.info(f"Step 2: Generating signals for portfolio {portfolio_id}...")
        signals_url = f"{STRATEGY_API_BASE}/strategy/generate-signals?portfolio_id={portfolio_id}"
        signals_response = call_api(signals_url)

        if signals_response:
            results["steps"].append({
                "step": "2",
                "name": "Generate Signals",
                "status": "completed",
                "message": f"Generated {signals_response.get('total_signals_generated', 0)} signals",
                "details": signals_response
            })
        else:
            raise HTTPException(status_code=500, detail="Signal generation failed")

        # Step 3: Execute trades for this portfolio
        logger.info(f"Step 3: Executing trades for portfolio {portfolio_id}...")
        execute_url = f"{PAPER_TRADING_API_BASE}/paper-trading/execute-signals?portfolio_id={portfolio_id}"
        execute_response = call_api(execute_url)

        if execute_response:
            results["steps"].append({
                "step": "3",
                "name": "Execute Trades",
                "status": "completed",
                "message": f"Executed {execute_response.get('execution_summary', {}).get('executed_trades', 0)} trades",
                "details": execute_response
            })
        else:
            raise HTTPException(status_code=500, detail="Trade execution failed")

        # Step 4: Update prices for this portfolio
        logger.info(f"Step 4: Updating prices for portfolio {portfolio_id}...")
        price_update_url = f"{PAPER_TRADING_API_BASE}/price-updater/update?portfolio_id={portfolio_id}"
        price_response = call_api(price_update_url)

        if price_response:
            results["steps"].append({
                "step": "4",
                "name": "Update Prices",
                "status": "completed",
                "message": f"Updated P&L for portfolio {portfolio_id}",
                "details": price_response
            })
        else:
            logger.warning(f"Price update failed for portfolio {portfolio_id}")
            results["steps"].append({
                "step": "4",
                "name": "Update Prices",
                "status": "failed",
                "message": "Price update failed"
            })

        # Step 5: Create portfolio snapshot
        logger.info(f"Step 5: Creating snapshot for portfolio {portfolio_id}...")
        portfolio_url = f"{PAPER_TRADING_API_BASE}/portfolios/{portfolio_id}"
        portfolio_response = call_api(portfolio_url)

        if portfolio_response:
            portfolio_data = portfolio_response.get('portfolio', {})
            # Convert to format expected by create_daily_portfolio_snapshot
            snapshot_data = {
                'balance': portfolio_data.get('current_balance', 0),
                'positions': portfolio_data.get('positions', []),
                'total_invested': portfolio_data.get('total_invested', 0),
                'total_profit_loss': portfolio_data.get('total_profit_loss', 0),
                'trade_count': portfolio_data.get('trade_count', 0)
            }
            create_daily_portfolio_snapshot(snapshot_data, portfolio_id=portfolio_id)
            results["steps"].append({
                "step": "5",
                "name": "Portfolio Snapshot",
                "status": "completed",
                "message": "Created portfolio snapshot"
            })
        else:
            results["steps"].append({
                "step": "5",
                "name": "Portfolio Snapshot",
                "status": "failed",
                "message": "Failed to create snapshot"
            })

        results["cycle_completed"] = datetime.now().isoformat()

        logger.info(f"=== PORTFOLIO {portfolio_id} TRADING CYCLE COMPLETED ===")

        return {
            "message": f"Portfolio trading cycle completed for {portfolio['name']}",
            "results": results,
            "summary": {
                "total_steps": len(results["steps"]),
                "successful_steps": len([s for s in results["steps"] if s["status"] == "completed"]),
                "failed_steps": len([s for s in results["steps"] if s["status"] == "failed"]),
                "overall_success": results["success"]
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in portfolio {portfolio_id} trading cycle: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Portfolio trading cycle error: {str(e)}")


@app.get("/trading/run-all-portfolios")
async def run_all_portfolios_cycle(
    # Event filtering parameters
    event_min_liquidity: float = 10000,
    event_min_volume: float = 50000,
    event_min_volume_24hr: Optional[float] = None,
    event_max_days_until_end: Optional[int] = None,
    event_min_days_until_end: Optional[int] = None,

    # Market filtering parameters
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    min_market_conviction: Optional[float] = 0.5,
    max_market_conviction: Optional[float] = 0.6
):
    """
    Run trading cycle for all active portfolios

    Returns:
        Results for all portfolio cycles
    """
    from src.db.operations import get_all_portfolios

    try:
        logger.info("=== STARTING TRADING CYCLE FOR ALL ACTIVE PORTFOLIOS ===")

        # Get all active portfolios
        portfolios = get_all_portfolios(status='active')

        if not portfolios:
            raise HTTPException(status_code=404, detail="No active portfolios found")

        logger.info(f"Running cycle for {len(portfolios)} active portfolios")

        # Ensure directories exist
        ensure_data_directories()

        all_results = {
            "cycle_started": datetime.now().isoformat(),
            "total_portfolios": len(portfolios),
            "portfolio_results": [],
            "shared_steps": [],
            "overall_success": True
        }

        # Step 1: Fetch and filter markets ONCE (shared across all portfolios)
        logger.info("Step 1: Fetching and filtering markets (shared)...")
        export_events_url = f"{EVENTS_API_BASE}/events/export-all-active-events-db"
        export_response = call_api(export_events_url)

        if export_response:
            all_results["shared_steps"].append({
                "step": "1a",
                "name": "Export Events",
                "status": "completed",
                "message": f"Exported {export_response.get('total_events', 0)} events"
            })
        else:
            raise HTTPException(status_code=500, detail="Event export failed")

        # Filter events
        filter_events_url = f"{EVENTS_API_BASE}/events/filter-trading-candidates-db"
        event_params = {
            "min_liquidity": event_min_liquidity,
            "min_volume": event_min_volume,
            "min_volume_24hr": event_min_volume_24hr,
            "max_days_until_end": event_max_days_until_end,
            "min_days_until_end": event_min_days_until_end
        }
        event_param_string = "&".join([f"{k}={v}" for k, v in event_params.items() if v is not None])
        filter_response = call_api(f"{filter_events_url}?{event_param_string}")

        if filter_response:
            all_results["shared_steps"].append({
                "step": "1b",
                "name": "Filter Events",
                "status": "completed",
                "message": f"Filtered {filter_response.get('total_candidates', 0)} candidates"
            })
        else:
            raise HTTPException(status_code=500, detail="Event filtering failed")

        # Filter markets
        markets_url = f"{MARKETS_API_BASE}/markets/export-filtered-markets-db"
        market_params = {
            "min_liquidity": min_liquidity,
            "min_volume": min_volume,
            "min_volume_24hr": min_volume_24hr,
            "min_market_conviction": min_market_conviction,
            "max_market_conviction": max_market_conviction
        }
        market_param_string = "&".join([f"{k}={v}" for k, v in market_params.items() if v is not None])
        markets_response = call_api(f"{markets_url}?{market_param_string}")

        if markets_response:
            all_results["shared_steps"].append({
                "step": "1c",
                "name": "Filter Markets",
                "status": "completed",
                "message": f"Filtered {markets_response.get('filtered_markets', 0)} markets"
            })
        else:
            raise HTTPException(status_code=500, detail="Market filtering failed")

        # Step 2: Run cycle for each portfolio
        for portfolio in portfolios:
            pid = portfolio['portfolio_id']
            pname = portfolio['name']

            logger.info(f"Running cycle for portfolio {pid}: {pname}")

            portfolio_result = {
                "portfolio_id": pid,
                "portfolio_name": pname,
                "steps": [],
                "success": True
            }

            try:
                # Generate signals for this portfolio
                signals_url = f"{STRATEGY_API_BASE}/strategy/generate-signals?portfolio_id={pid}"
                signals_response = call_api(signals_url)

                if signals_response:
                    portfolio_result["steps"].append({
                        "step": "2",
                        "name": "Generate Signals",
                        "status": "completed",
                        "signals_generated": signals_response.get('total_signals_generated', 0)
                    })
                else:
                    portfolio_result["steps"].append({
                        "step": "2",
                        "name": "Generate Signals",
                        "status": "failed"
                    })
                    portfolio_result["success"] = False

                # Execute trades for this portfolio
                execute_url = f"{PAPER_TRADING_API_BASE}/paper-trading/execute-signals?portfolio_id={pid}"
                execute_response = call_api(execute_url)

                if execute_response:
                    portfolio_result["steps"].append({
                        "step": "3",
                        "name": "Execute Trades",
                        "status": "completed",
                        "trades_executed": execute_response.get('execution_summary', {}).get('executed_trades', 0)
                    })
                else:
                    portfolio_result["steps"].append({
                        "step": "3",
                        "name": "Execute Trades",
                        "status": "failed"
                    })
                    portfolio_result["success"] = False

                # Update prices for this portfolio
                price_update_url = f"{PAPER_TRADING_API_BASE}/price-updater/update?portfolio_id={pid}"
                price_response = call_api(price_update_url)

                if price_response:
                    portfolio_result["steps"].append({
                        "step": "4",
                        "name": "Update Prices",
                        "status": "completed"
                    })
                else:
                    portfolio_result["steps"].append({
                        "step": "4",
                        "name": "Update Prices",
                        "status": "failed"
                    })

                logger.info(f"✓ Completed cycle for portfolio {pid}: {pname}")

            except Exception as portfolio_error:
                logger.error(f"Error in portfolio {pid} cycle: {portfolio_error}")
                portfolio_result["success"] = False
                portfolio_result["error"] = str(portfolio_error)
                all_results["overall_success"] = False

            all_results["portfolio_results"].append(portfolio_result)

        all_results["cycle_completed"] = datetime.now().isoformat()

        # Calculate summary
        successful_portfolios = len([p for p in all_results["portfolio_results"] if p["success"]])
        failed_portfolios = len([p for p in all_results["portfolio_results"] if not p["success"]])

        logger.info(f"=== ALL PORTFOLIOS CYCLE COMPLETED: {successful_portfolios}/{len(portfolios)} successful ===")

        return {
            "message": f"Trading cycle completed for {len(portfolios)} portfolios",
            "results": all_results,
            "summary": {
                "total_portfolios": len(portfolios),
                "successful_portfolios": successful_portfolios,
                "failed_portfolios": failed_portfolios,
                "overall_success": all_results["overall_success"]
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in all-portfolios cycle: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"All-portfolios cycle error: {str(e)}")


@app.get("/trading/run-full-cycle")
async def run_full_trading_cycle(
    # Event filtering parameters
    event_min_liquidity: float = 10000,
    event_min_volume: float = 50000,
    event_min_volume_24hr: Optional[float] = None,
    event_max_days_until_end: Optional[int] = None,
    event_min_days_until_end: Optional[int] = None,

    # Market filtering parameters
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    min_market_conviction: Optional[float] = 0.5,
    max_market_conviction: Optional[float] = 0.6
):
    """
    Run complete automated trading cycle with full control over filtering parameters
    
    Event Filtering Args:
        event_min_liquidity: Minimum liquidity threshold for event filtering
        event_min_volume: Minimum volume threshold for event filtering  
        event_min_volume_24hr: Minimum 24hr volume threshold for event filtering
        event_max_days_until_end: Maximum days until event ends
        event_min_days_until_end: Minimum days until event ends
        
    Market Filtering Args:
        min_liquidity: Minimum liquidity threshold for market filtering
        min_volume: Minimum volume threshold for market filtering
        min_volume_24hr: Minimum 24hr volume threshold for market filtering
        min_market_conviction: Minimum market conviction threshold
        max_market_conviction: Maximum market conviction threshold
        
    Returns:
        Complete trading cycle results with all step details
    """
    try:
        logger.info("=== STARTING FULL TRADING CYCLE ===")
        
        # Ensure directories exist
        ensure_data_directories()
        
        results = {
            "cycle_started": datetime.now().isoformat(),
            "steps": [],
            "success": True,
            "error_details": None
        }
        
        # Step 1a: Export all active events (fetch and save raw events)
        logger.info("Step 1a: Exporting all active events...")
        export_events_url = f"{EVENTS_API_BASE}/events/export-all-active-events-db"
        export_response = call_api(export_events_url)
        
        if export_response:
            results["steps"].append({
                "step": "1a",
                "name": "Export All Active Events",
                "status": "completed",
                "message": f"Exported {export_response.get('total_events', 0)} raw events",
                "details": {
                    "file_path": export_response.get('file_path'),
                    "total_events": export_response.get('total_events', 0),
                    "timestamp": export_response.get('timestamp')
                }
            })
        else:
            results["success"] = False
            results["steps"].append({
                "step": "1a",
                "name": "Export All Active Events",
                "status": "failed",
                "message": "Failed to export active events"
            })
            raise HTTPException(status_code=500, detail="Active events export failed")
        
        # Step 1b: Filter events for trading candidates
        logger.info("Step 1b: Filtering events for trading candidates...")
        filter_events_url = f"{EVENTS_API_BASE}/events/filter-trading-candidates-db"
        event_params = {
            "min_liquidity": event_min_liquidity,
            "min_volume": event_min_volume,
            "min_volume_24hr": event_min_volume_24hr,
            "max_days_until_end": event_max_days_until_end,
            "min_days_until_end": event_min_days_until_end
        }
        # Add params to URL (only non-None values)
        event_param_string = "&".join([f"{k}={v}" for k, v in event_params.items() if v is not None])
        filter_response = call_api(f"{filter_events_url}?{event_param_string}")
        
        if filter_response:
            results["steps"].append({
                "step": "1b",
                "name": "Filter Events",
                "status": "completed",
                "message": f"Filtered {filter_response.get('total_candidates', 0)} trading candidates",
                "details": {
                    "total_original_events": filter_response.get('total_original_events', 0),
                    "total_candidates": filter_response.get('total_candidates', 0),
                    "source_file": filter_response.get('source_file'),
                    "output_file": filter_response.get('output_file'),
                    "filtering_criteria": event_params,
                    "summary_stats": filter_response.get('summary_stats', {})
                }
            })
        else:
            results["success"] = False
            results["steps"].append({
                "step": "1b",
                "name": "Filter Events",
                "status": "failed",
                "message": "Failed to filter events for trading candidates"
            })
            raise HTTPException(status_code=500, detail="Event filtering failed")
        
        # Step 3: Filter Markets with user-controlled parameters
        logger.info("Step 3: Filtering markets...")
        markets_url = f"{MARKETS_API_BASE}/markets/export-filtered-markets-db"
        market_params = {
            "min_liquidity": min_liquidity,
            "min_volume": min_volume,
            "min_volume_24hr": min_volume_24hr,
            "min_market_conviction": min_market_conviction,
            "max_market_conviction": max_market_conviction
        }
        # Add params to URL (only non-None values)
        market_param_string = "&".join([f"{k}={v}" for k, v in market_params.items() if v is not None])
        markets_response = call_api(f"{markets_url}?{market_param_string}")
        
        if markets_response:
            results["steps"].append({
                "step": "2",
                "name": "Filter Markets",
                "status": "completed",
                "message": f"Filtered {markets_response.get('fetched_detailed_markets', 0)} markets",
                "details": {
                    "total_original_markets": markets_response.get('total_original_markets', 0),
                    "filtered_markets": markets_response.get('filtered_markets', 0),
                    "fetched_detailed_markets": markets_response.get('fetched_detailed_markets', 0),
                    "filtering_criteria": market_params
                }
            })
        else:
            results["success"] = False
            results["steps"].append({
                "step": "2",
                "name": "Filter Markets",
                "status": "failed",
                "message": "Failed to filter markets"
            })
            raise HTTPException(status_code=500, detail="Market filtering failed")
        
        # Step 4: Generate Trading Signals
        logger.info("Step 4: Generating trading signals...")
        signals_url = f"{STRATEGY_API_BASE}/strategy/generate-signals"
        signals_response = call_api(signals_url)
        
        if signals_response:
            results["steps"].append({
                "step": "3",
                "name": "Generate Signals",
                "status": "completed",
                "message": f"Generated {signals_response.get('total_signals_generated', 0)} signals",
                "details": {
                    "total_markets_analyzed": signals_response.get('total_markets_analyzed', 0),
                    "total_signals_generated": signals_response.get('total_signals_generated', 0),
                    "signal_breakdown": signals_response.get('signal_breakdown', {}),
                    "summary_stats": signals_response.get('summary_stats', {})
                }
            })
        else:
            results["success"] = False
            results["steps"].append({
                "step": "3",
                "name": "Generate Signals",
                "status": "failed",
                "message": "Failed to generate trading signals"
            })
            raise HTTPException(status_code=500, detail="Signal generation failed")
        
        # Step 5: Execute Paper Trades
        logger.info("Step 5: Executing paper trades...")
        execute_url = f"{PAPER_TRADING_API_BASE}/paper-trading/execute-signals"
        execute_response = call_api(execute_url)
        
        if execute_response:
            results["steps"].append({
                "step": "4",
                "name": "Execute Paper Trades",
                "status": "completed",
                "message": f"Executed {execute_response.get('execution_summary', {}).get('executed_trades', 0)} trades",
                "details": {
                    "execution_summary": execute_response.get('execution_summary', {}),
                    "portfolio_update": execute_response.get('portfolio_update', {})
                }
            })
        else:
            results["success"] = False
            results["steps"].append({
                "step": "4",
                "name": "Execute Paper Trades",
                "status": "failed",
                "message": "Failed to execute paper trades"
            })
            raise HTTPException(status_code=500, detail="Paper trading execution failed")
        
        # Step 6: Update Portfolio P&L and Create Snapshot
        logger.info("Step 6: Creating portfolio snapshot...")
        portfolio_url = f"{PAPER_TRADING_API_BASE}/paper-trading/portfolio"
        portfolio_response = call_api(portfolio_url)
        
        if portfolio_response:
            portfolio_data = portfolio_response.get('portfolio', {})
            create_daily_portfolio_snapshot(portfolio_data)
            results["steps"].append({
                "step": "5",
                "name": "Portfolio Snapshot",
                "status": "completed",
                "message": "Created daily portfolio snapshot",
                "details": {
                    "portfolio_summary": portfolio_response.get('summary', {})
                }
            })
        else:
            results["steps"].append({
                "step": "5",
                "name": "Portfolio Snapshot",
                "status": "failed",
                "message": "Failed to create portfolio snapshot"
            })
        
        # Step 7: Archive Signals
        logger.info("Step 7: Archiving trading signals...")
        try:
            archive_current_signals()
            results["steps"].append({
                "step": "6",
                "name": "Archive Signals",
                "status": "completed",
                "message": "Archived current signals to monthly file"
            })
        except Exception as archive_error:
            results["steps"].append({
                "step": "6",
                "name": "Archive Signals",
                "status": "failed",
                "message": f"Failed to archive signals: {str(archive_error)}"
            })
        
        results["cycle_completed"] = datetime.now().isoformat()
        
        logger.info("=== FULL TRADING CYCLE COMPLETED SUCCESSFULLY ===")
        
        return {
            "message": "Full trading cycle completed successfully",
            "results": results,
            "summary": {
                "total_steps": len(results["steps"]),
                "successful_steps": len([s for s in results["steps"] if s["status"] == "completed"]),
                "failed_steps": len([s for s in results["steps"] if s["status"] == "failed"]),
                "overall_success": results["success"]
            },
            "applied_parameters": {
                "event_filtering": {
                    "event_min_liquidity": event_min_liquidity,
                    "event_min_volume": event_min_volume,
                    "event_min_volume_24hr": event_min_volume_24hr,
                    "event_max_days_until_end": event_max_days_until_end,
                    "event_min_days_until_end": event_min_days_until_end
                },
                "market_filtering": {
                    "min_liquidity": min_liquidity,
                    "min_volume": min_volume,
                    "min_volume_24hr": min_volume_24hr,
                    "min_market_conviction": min_market_conviction,
                    "max_market_conviction": max_market_conviction
                }
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR IN FULL TRADING CYCLE ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/trading/status")
async def get_trading_status():
    """
    Get comprehensive status of entire trading system
    
    Returns:
        Status of all trading components
    """
    try:
        logger.info("Getting comprehensive trading system status...")
        
        status = {
            "timestamp": datetime.now().isoformat(),
            "system_health": "unknown",
            "components": {}
        }
        
        # Check Events Controller
        events_response = call_api(f"{EVENTS_API_BASE}/", timeout=10)
        status["components"]["events_controller"] = {
            "status": "online" if events_response else "offline",
            "api_base": EVENTS_API_BASE
        }
        
        # Check Markets Controller
        markets_response = call_api(f"{MARKETS_API_BASE}/markets/status", timeout=10)
        status["components"]["markets_controller"] = {
            "status": "online" if markets_response else "offline",
            "api_base": MARKETS_API_BASE,
            "details": markets_response if markets_response else None
        }
        
        # Check Strategy Controller
        strategy_response = call_api(f"{STRATEGY_API_BASE}/strategy/status", timeout=10)
        status["components"]["strategy_controller"] = {
            "status": "online" if strategy_response else "offline",
            "api_base": STRATEGY_API_BASE,
            "details": strategy_response if strategy_response else None
        }
        
        # Check Paper Trading Controller
        paper_trading_response = call_api(f"{PAPER_TRADING_API_BASE}/paper-trading/status", timeout=10)
        status["components"]["paper_trading_controller"] = {
            "status": "online" if paper_trading_response else "offline",
            "api_base": PAPER_TRADING_API_BASE,
            "details": paper_trading_response if paper_trading_response else None
        }
        
        # Determine overall system health
        online_components = len([c for c in status["components"].values() if c["status"] == "online"])
        total_components = len(status["components"])
        
        if online_components == total_components:
            status["system_health"] = "healthy"
        elif online_components > 0:
            status["system_health"] = "degraded"
        else:
            status["system_health"] = "down"
        
        status["health_summary"] = {
            "online_components": online_components,
            "total_components": total_components,
            "health_percentage": round((online_components / total_components) * 100, 1)
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting trading status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting trading status: {str(e)}")

@app.get("/trading/performance-summary")
async def get_performance_summary():
    """
    Get trading performance summary from historical data
    
    Returns:
        Performance metrics and summary
    """
    try:
        logger.info("Generating performance summary...")
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "portfolio_performance": {},
            "trading_history": {},
            "signals_history": {}
        }
        
        # Portfolio History (from database)
        try:
            portfolio_history = get_portfolio_history(limit=100)  # Get last 100 snapshots

            if portfolio_history:
                latest = portfolio_history[0]  # Most recent first
                first = portfolio_history[-1]  # Oldest last

                summary["portfolio_performance"] = {
                    "days_tracked": len(portfolio_history),
                    "starting_balance": first.get('balance', 0),
                    "current_total_value": latest.get('total_value', 0),
                    "total_profit_loss": latest.get('total_profit_loss', 0),
                    "total_invested": latest.get('total_invested', 0),
                    "current_open_positions": latest.get('open_positions', 0),
                    "total_trades": latest.get('trade_count', 0)
                }
        except Exception as e:
            logger.warning(f"Could not load portfolio history from database: {e}")
        
        # Trading History (from database)
        try:
            trades = get_trades(limit=1000)  # Get last 1000 trades

            summary["trading_history"] = {
                "total_trades": len(trades),
                "total_amount_traded": sum(trade.get('amount', 0) for trade in trades),
                "buy_yes_trades": len([t for t in trades if t.get('action') == 'buy_yes']),
                "buy_no_trades": len([t for t in trades if t.get('action') == 'buy_no'])
            }
        except Exception as e:
            logger.warning(f"Could not load trading history from database: {e}")
        
        # Current Portfolio
        portfolio_response = call_api(f"{PAPER_TRADING_API_BASE}/paper-trading/portfolio", timeout=10)
        if portfolio_response:
            summary["current_portfolio"] = portfolio_response.get('summary', {})
        
        return {
            "message": "Performance summary generated",
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating performance summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating performance summary: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
    # uvicorn src.trading_controller:app --reload --port 8000