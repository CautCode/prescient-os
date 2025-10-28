# Paper Trading Controller - Executes virtual trades, manages portfolio, tracks P&L
# Main functions: execute_signals(), get_portfolio(), execute_trade(), update_portfolio_pnl()
# Used by: trading_controller.py for simulated trade execution and portfolio management

from fastapi import FastAPI, HTTPException
from typing import Dict, List, Optional
import json
import os
from datetime import datetime
import logging

# Set up logging
log_level = getattr(logging, os.getenv('PYTHON_LOG_LEVEL', 'INFO'))
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Polymarket Paper Trading API", version="1.0.0")

# Import price updater
from src.price_updater import start_price_updater, stop_price_updater, get_price_updater

# FastAPI lifecycle events
@app.on_event("startup")
async def startup_event():
    """Start price updater when app starts"""
    # Get update interval from environment variable (default 5 minutes)
    update_interval = int(os.getenv('PRICE_UPDATE_INTERVAL', '300'))
    start_price_updater(update_interval)
    logger.info(f"✓ Price updater started with {update_interval}s interval")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop price updater when app shuts down"""
    stop_price_updater()
    logger.info("Price updater stopped")

# Helper Functions
def ensure_data_directories():
    """
    Create necessary data directories if they don't exist
    """
    os.makedirs("data/trades", exist_ok=True)
    os.makedirs("data/history", exist_ok=True)

def initialize_portfolio() -> Dict:
    """
    Initialize portfolio with starting balance
    
    Returns:
        Initial portfolio state
    """
    return {
        "balance": 10000.0,  # Start with $10,000 virtual money
        "positions": [],
        "total_invested": 0.0,
        "total_profit_loss": 0.0,
        "trade_count": 0,
        "created_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat()
    }

def load_portfolio() -> Dict:
    """
    Load portfolio from database

    Returns:
        Portfolio state dictionary
    """
    from src.db.operations import get_portfolio_state, get_portfolio_positions

    try:
        # Get portfolio state from DB
        portfolio_state = get_portfolio_state()

        # Get open positions from DB
        positions = get_portfolio_positions(status='open')

        # Build portfolio dict matching existing format
        portfolio = {
            "balance": portfolio_state['balance'],
            "positions": positions,
            "total_invested": portfolio_state['total_invested'],
            "total_profit_loss": portfolio_state['total_profit_loss'],
            "trade_count": portfolio_state['trade_count'],
            "created_at": portfolio_state['created_at'].isoformat() if isinstance(portfolio_state['created_at'], datetime) else portfolio_state['created_at'],
            "last_updated": portfolio_state['last_updated'].isoformat() if isinstance(portfolio_state['last_updated'], datetime) else portfolio_state['last_updated']
        }
        logger.debug(f"Loaded portfolio from database with balance: ${portfolio.get('balance', 0):.2f}")
        return portfolio
    except Exception as e:
        logger.error(f"Error loading portfolio from database: {e}")
        raise

def save_portfolio(portfolio: Dict):
    """
    Save portfolio to database

    Args:
        portfolio: Portfolio state dictionary
    """
    from src.db.operations import upsert_portfolio_state

    try:
        upsert_portfolio_state(portfolio)
        logger.debug(f"Saved portfolio to database with balance: ${portfolio.get('balance', 0):.2f}")
    except Exception as e:
        logger.error(f"Error saving portfolio to database: {e}")
        raise

def execute_trade(signal: Dict, portfolio: Dict) -> Dict:
    """
    Execute a single trade based on signal
    
    Args:
        signal: Trading signal dictionary
        portfolio: Current portfolio state
        
    Returns:
        Trade execution result
    """
    trade_amount = signal.get('amount', 100)
    
    # Check if sufficient balance
    if portfolio['balance'] < trade_amount:
        return {
            "status": "failed",
            "reason": f"Insufficient balance. Required: ${trade_amount}, Available: ${portfolio['balance']:.2f}",
            "trade": None
        }
    
    # Create trade record
    trade = {
        "trade_id": f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{signal['market_id']}",
        "timestamp": datetime.now().isoformat(),
        "market_id": signal['market_id'],
        "market_question": signal['market_question'],
        "action": signal['action'],
        "amount": trade_amount,
        "entry_price": signal['target_price'],
        "confidence": signal['confidence'],
        "reason": signal['reason'],
        "status": "open",
        "event_id": signal.get('event_id'),
        "event_title": signal.get('event_title'),
        "event_end_date": signal.get('event_end_date'),
        "current_pnl": 0.0,
        "realized_pnl": None
    }
    
    # Update portfolio
    portfolio['balance'] -= trade_amount
    portfolio['total_invested'] += trade_amount
    portfolio['trade_count'] += 1
    
    # Add position to portfolio
    position = {
        "trade_id": trade["trade_id"],
        "market_id": signal['market_id'],
        "market_question": signal['market_question'],
        "action": signal['action'],
        "amount": trade_amount,
        "entry_price": signal['target_price'],
        "entry_timestamp": trade["timestamp"],
        "status": "open",
        "current_pnl": 0.0
    }
    portfolio['positions'].append(position)
    
    return {
        "status": "executed",
        "reason": "Trade executed successfully",
        "trade": trade
    }

def append_trade_to_history(trade: Dict):
    """
    Append executed trade to permanent trade history in database

    Args:
        trade: Trade dictionary to append
    """
    from src.db.operations import insert_trade, add_portfolio_position

    try:
        # Insert trade into trades table
        insert_trade(trade)

        # Add position to portfolio_positions table
        position = {
            "trade_id": trade["trade_id"],
            "market_id": trade['market_id'],
            "market_question": trade['market_question'],
            "action": trade['action'],
            "amount": trade['amount'],
            "entry_price": trade['entry_price'],
            "entry_timestamp": trade["timestamp"],
            "status": "open",
            "current_pnl": 0.0
        }
        add_portfolio_position(position)

        logger.debug(f"Inserted trade {trade['trade_id']} into database")

    except Exception as e:
        logger.error(f"Error appending trade to database: {e}")
        raise

def update_portfolio_pnl(portfolio: Dict, current_market_data: Optional[List[Dict]] = None):
    """
    Update portfolio P&L based on current market prices
    
    Args:
        portfolio: Portfolio state
        current_market_data: Optional current market data for P&L calculation
    """
    if not current_market_data:
        logger.debug("No current market data provided, skipping P&L update")
        return
    
    # Create market price lookup
    market_prices = {}
    for market in current_market_data:
        market_id = market.get('id')
        if market_id:
            try:
                outcome_prices_str = market.get('outcomePrices', '[]')
                import ast
                outcome_prices = ast.literal_eval(outcome_prices_str)
                if len(outcome_prices) >= 2:
                    market_prices[market_id] = {
                        'yes_price': float(outcome_prices[0]),
                        'no_price': float(outcome_prices[1])
                    }
            except:
                continue
    
    # Update P&L for each position
    total_unrealized_pnl = 0.0
    for position in portfolio['positions']:
        if position['status'] != 'open':
            continue
            
        market_id = position['market_id']
        if market_id not in market_prices:
            continue
            
        current_prices = market_prices[market_id]
        entry_price = position['entry_price']
        amount = position['amount']
        action = position['action']
        
        # Calculate current value based on action
        if action == 'buy_yes':
            current_price = current_prices['yes_price']
        elif action == 'buy_no':
            current_price = current_prices['no_price']
        else:
            continue
        
        # Calculate P&L: (current_price - entry_price) * amount
        pnl = (current_price - entry_price) * amount
        position['current_pnl'] = round(pnl, 2)
        total_unrealized_pnl += pnl
    
    # Update portfolio total P&L
    portfolio['total_profit_loss'] = round(total_unrealized_pnl, 2)
    logger.debug(f"Updated portfolio P&L: ${total_unrealized_pnl:.2f}")

# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Polymarket Paper Trading API is running", "timestamp": datetime.now().isoformat()}

@app.get("/paper-trading/execute-signals")
async def execute_signals():
    """
    Execute all current trading signals
    
    Returns:
        Execution results and portfolio update
    """
    try:
        logger.info("=== STARTING PAPER TRADING EXECUTION ===")
        
        # Ensure directories exist
        ensure_data_directories()
        
        # Step 1: Load current signals
        signals_path = os.path.join("data", "trades", "current_signals.json")
        logger.info(f"Reading trading signals from: {signals_path}")
        
        try:
            with open(signals_path, "r", encoding="utf-8") as f:
                signals = json.load(f)
            logger.info(f"✓ Successfully loaded {len(signals)} trading signals")
        except Exception as read_error:
            logger.error(f"✗ Error reading signals file: {read_error}")
            raise HTTPException(status_code=500, detail=f"Error reading signals file: {str(read_error)}")
        
        if not signals:
            logger.warning("No trading signals found")
            raise HTTPException(status_code=404, detail="No trading signals found. Please generate signals first.")
        
        # Step 2: Load portfolio
        logger.info("Step 2: Loading portfolio...")
        portfolio = load_portfolio()
        initial_balance = portfolio['balance']
        logger.info(f"✓ Loaded portfolio with balance: ${initial_balance:.2f}")
        
        # Step 3: Execute trades
        logger.info("Step 3: Executing trades...")
        execution_results = []
        executed_trades = []
        
        for signal in signals:
            try:
                result = execute_trade(signal, portfolio)
                execution_results.append({
                    "market_id": signal['market_id'],
                    "market_question": signal.get('market_question', 'Unknown'),
                    "action": signal['action'],
                    "amount": signal['amount'],
                    "status": result['status'],
                    "reason": result['reason']
                })
                
                if result['status'] == 'executed' and result['trade']:
                    executed_trades.append(result['trade'])
                    logger.debug(f"Executed: {signal['action']} {signal['market_id']} for ${signal['amount']}")
                else:
                    logger.debug(f"Failed: {signal['market_id']} - {result['reason']}")
                    
            except Exception as trade_error:
                logger.warning(f"Error executing trade for market {signal.get('market_id', 'unknown')}: {trade_error}")
                execution_results.append({
                    "market_id": signal.get('market_id', 'unknown'),
                    "market_question": signal.get('market_question', 'Unknown'),
                    "action": signal.get('action', 'unknown'),
                    "amount": signal.get('amount', 0),
                    "status": "error",
                    "reason": str(trade_error)
                })
        
        # Step 4: Save portfolio
        logger.info("Step 4: Saving updated portfolio...")
        try:
            save_portfolio(portfolio)
            logger.info(f"✓ Portfolio saved. New balance: ${portfolio['balance']:.2f}")
        except Exception as save_error:
            logger.error(f"✗ Error saving portfolio: {save_error}")
            raise HTTPException(status_code=500, detail=f"Error saving portfolio: {str(save_error)}")
        
        # Step 5: Append trades to history
        logger.info("Step 5: Saving trades to permanent history...")
        try:
            for trade in executed_trades:
                append_trade_to_history(trade)
            logger.info(f"✓ Appended {len(executed_trades)} trades to history")
        except Exception as history_error:
            logger.error(f"✗ Error saving trade history: {history_error}")
            # Don't fail the entire operation for history save errors
            logger.warning("Continuing despite history save error")
        
        # Step 6: Calculate summary
        logger.info("Step 6: Calculating execution summary...")
        executed_count = len(executed_trades)
        failed_count = len([r for r in execution_results if r['status'] == 'failed'])
        error_count = len([r for r in execution_results if r['status'] == 'error'])
        total_invested = sum(trade['amount'] for trade in executed_trades)
        
        logger.info("=== PAPER TRADING EXECUTION COMPLETED ===")
        
        return {
            "message": "Paper trading execution completed",
            "execution_summary": {
                "total_signals": len(signals),
                "executed_trades": executed_count,
                "failed_trades": failed_count,
                "error_trades": error_count,
                "total_invested": total_invested
            },
            "portfolio_update": {
                "initial_balance": initial_balance,
                "final_balance": portfolio['balance'],
                "amount_invested": total_invested,
                "total_positions": len(portfolio['positions']),
                "total_trades_count": portfolio['trade_count']
            },
            "execution_details": execution_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR IN PAPER TRADING EXECUTION ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/paper-trading/portfolio")
async def get_portfolio():
    """
    Get current portfolio state
    
    Returns:
        Current portfolio information
    """
    try:
        portfolio = load_portfolio()
        
        # Try to update P&L with current market data if available
        try:
            markets_path = os.path.join("data", "markets", "filtered_markets.json")
            if os.path.exists(markets_path):
                with open(markets_path, "r", encoding="utf-8") as f:
                    market_data = json.load(f)
                update_portfolio_pnl(portfolio, market_data)
                save_portfolio(portfolio)  # Save updated P&L
        except Exception as pnl_error:
            logger.debug(f"Could not update P&L: {pnl_error}")
        
        return {
            "message": "Current portfolio retrieved",
            "portfolio": portfolio,
            "summary": {
                "total_value": portfolio['balance'] + portfolio.get('total_profit_loss', 0),
                "open_positions": len([p for p in portfolio['positions'] if p['status'] == 'open']),
                "total_invested": portfolio['total_invested'],
                "unrealized_pnl": portfolio.get('total_profit_loss', 0)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting portfolio: {str(e)}")

@app.get("/paper-trading/trades-history")
async def get_trades_history():
    """
    Get complete trading history from database

    Returns:
        All executed trades history
    """
    from src.db.operations import get_trades

    try:
        trades_history = get_trades()

        return {
            "message": "Trading history retrieved from database",
            "trades_count": len(trades_history),
            "trades": trades_history,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting trades history from database: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting trades history: {str(e)}")

@app.get("/paper-trading/update-prices")
async def update_prices():
    """
    Manually trigger price update for open positions

    Returns:
        Price update result
    """
    try:
        updater = get_price_updater()
        if updater:
            logger.info("Manual price update triggered")
            updater.update_open_positions_prices()

            # Get updated portfolio
            portfolio = load_portfolio()

            return {
                "message": "Price update completed",
                "portfolio_pnl": portfolio.get('total_profit_loss', 0),
                "open_positions": len([p for p in portfolio.get('positions', []) if p.get('status') == 'open']),
                "last_price_update": portfolio.get('last_price_update'),
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=503, detail="Price updater not running")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating prices: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating prices: {str(e)}")

@app.get("/paper-trading/status")
async def get_paper_trading_status():
    """
    Get status of paper trading system from database

    Returns:
        Status information about portfolio and trades
    """
    from src.db.operations import get_trades

    try:
        status = {
            "timestamp": datetime.now().isoformat(),
            "portfolio_exists": False,
            "portfolio_balance": 0.0,
            "open_positions": 0,
            "total_trades": 0,
            "trades_history_exists": False,
            "price_updater_running": False,
            "price_update_interval": None
        }

        # Check price updater status
        updater = get_price_updater()
        if updater:
            status["price_updater_running"] = updater.running
            status["price_update_interval"] = updater.update_interval

        # Check portfolio from database
        try:
            portfolio = load_portfolio()
            status["portfolio_exists"] = True
            status["portfolio_balance"] = portfolio.get('balance', 0.0)
            status["open_positions"] = len([p for p in portfolio.get('positions', []) if p.get('status') == 'open'])
            status["total_trades"] = portfolio.get('trade_count', 0)
            status["portfolio_last_updated"] = portfolio.get('last_updated')
            status["last_price_update"] = portfolio.get('last_price_update')
        except:
            pass

        # Check trades history from database
        try:
            trades_history = get_trades()
            status["trades_history_exists"] = True
            status["trades_in_history"] = len(trades_history)
        except:
            pass

        return status

    except Exception as e:
        logger.error(f"Error getting paper trading status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting paper trading status: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
    # uvicorn src.paper_trading_controller:app --reload --port 8003