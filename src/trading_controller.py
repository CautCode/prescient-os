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

def create_daily_portfolio_snapshot(portfolio_data: Dict):
    """
    Create daily portfolio snapshot for historical tracking
    
    Args:
        portfolio_data: Current portfolio state
    """
    try:
        history_path = os.path.join("data", "history", "portfolio_history.json")
        
        # Load existing history or start with empty list
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
        
        # Create snapshot
        snapshot = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "balance": portfolio_data.get('balance', 0),
            "total_invested": portfolio_data.get('total_invested', 0),
            "total_profit_loss": portfolio_data.get('total_profit_loss', 0),
            "total_value": portfolio_data.get('balance', 0) + portfolio_data.get('total_profit_loss', 0),
            "open_positions": len([p for p in portfolio_data.get('positions', []) if p.get('status') == 'open']),
            "trade_count": portfolio_data.get('trade_count', 0)
        }
        
        # Append snapshot (APPEND ONLY as per MVP spec)
        history.append(snapshot)
        
        # Save back to file
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Created daily portfolio snapshot: ${snapshot['total_value']:.2f} total value")
        
    except Exception as e:
        logger.error(f"Error creating portfolio snapshot: {e}")

def archive_current_signals():
    """
    Archive current signals to monthly file
    """
    try:
        signals_path = os.path.join("data", "trades", "current_signals.json")
        if not os.path.exists(signals_path):
            return
        
        # Read current signals
        with open(signals_path, "r", encoding="utf-8") as f:
            signals = json.load(f)
        
        if not signals:
            return
        
        # Create monthly archive filename
        current_month = datetime.now().strftime("%Y-%m")
        archive_path = os.path.join("data", "history", f"signals_archive_{current_month}.json")
        
        # Load existing archive or start with empty list
        if os.path.exists(archive_path):
            with open(archive_path, "r", encoding="utf-8") as f:
                archive = json.load(f)
        else:
            archive = []
        
        # Add signals with archive timestamp
        archive_entry = {
            "archived_at": datetime.now().isoformat(),
            "signals_count": len(signals),
            "signals": signals
        }
        archive.append(archive_entry)
        
        # Save archive (NEW FILE MONTHLY as per MVP spec)
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(archive, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Archived {len(signals)} signals to {archive_path}")
        
    except Exception as e:
        logger.error(f"Error archiving signals: {e}")

# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Polymarket Trading Controller API is running", "timestamp": datetime.now().isoformat()}

@app.get("/trading/run-full-cycle")
async def run_full_trading_cycle(
    # Event filtering parameters
    event_min_liquidity: float = 10000,
    event_min_volume: float = 50000,
    event_min_volume_24hr: Optional[float] = None,
    event_max_days_until_end: int = 90,
    event_min_days_until_end: int = 1,
    
    # Market filtering parameters  
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    min_market_conviction: Optional[float] = None,
    max_market_conviction: Optional[float] = None
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
        export_events_url = f"{EVENTS_API_BASE}/events/export-all-active-events-json"
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
        filter_events_url = f"{EVENTS_API_BASE}/events/filter-trading-candidates-json"
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
        markets_url = f"{MARKETS_API_BASE}/markets/export-filtered-markets-json"
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
        
        # Portfolio History
        portfolio_history_path = os.path.join("data", "history", "portfolio_history.json")
        if os.path.exists(portfolio_history_path):
            with open(portfolio_history_path, "r", encoding="utf-8") as f:
                portfolio_history = json.load(f)
            
            if portfolio_history:
                latest = portfolio_history[-1]
                first = portfolio_history[0]
                
                summary["portfolio_performance"] = {
                    "days_tracked": len(portfolio_history),
                    "starting_balance": first.get('balance', 0),
                    "current_total_value": latest.get('total_value', 0),
                    "total_profit_loss": latest.get('total_profit_loss', 0),
                    "total_invested": latest.get('total_invested', 0),
                    "current_open_positions": latest.get('open_positions', 0),
                    "total_trades": latest.get('trade_count', 0)
                }
        
        # Trading History
        trades_path = os.path.join("data", "trades", "paper_trades.json")
        if os.path.exists(trades_path):
            with open(trades_path, "r", encoding="utf-8") as f:
                trades = json.load(f)
            
            summary["trading_history"] = {
                "total_trades": len(trades),
                "total_amount_traded": sum(trade.get('amount', 0) for trade in trades),
                "buy_yes_trades": len([t for t in trades if t.get('action') == 'buy_yes']),
                "buy_no_trades": len([t for t in trades if t.get('action') == 'buy_no'])
            }
        
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
    # uvicorn src.trading_controller:app --reload --port 8