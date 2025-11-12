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
        market_id = market.get('id') or market.get('market_id')
        if market_id and market.get('yes_price') is not None and market.get('no_price') is not None:
            market_prices[market_id] = {
                'yes_price': float(market['yes_price']),
                'no_price': float(market['no_price'])
            }
    
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
async def execute_signals(portfolio_id: Optional[int] = None):
    """
    Execute all current trading signals for a specific portfolio or default portfolio

    Args:
        portfolio_id: Portfolio ID (optional, defaults to first active portfolio)

    Returns:
        Execution results and portfolio update
    """
    from src.db.operations import (
        get_current_signals, get_portfolio_state, get_portfolio_positions,
        update_portfolio, add_portfolio_position, insert_trade, mark_signal_executed
    )

    try:
        logger.info("=== STARTING PAPER TRADING EXECUTION ===")

        # Step 1: Get portfolio state from database
        logger.info("Step 1: Loading portfolio from database...")
        try:
            portfolio = get_portfolio_state(portfolio_id)
            portfolio_id = portfolio['portfolio_id']  # Use the actual ID (in case None was passed)
            logger.info(f"✓ Loaded portfolio {portfolio_id}: {portfolio['name']} with balance: ${portfolio['current_balance']:.2f}")
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))

        # Step 2: Load current signals from database for this portfolio
        logger.info("Step 2: Reading trading signals from database...")
        try:
            signals = get_current_signals(portfolio_id=portfolio_id, executed=False)
            logger.info(f"✓ Successfully loaded {len(signals)} trading signals for portfolio {portfolio_id}")
        except Exception as read_error:
            logger.error(f"✗ Error reading signals from database: {read_error}")
            raise HTTPException(status_code=500, detail=f"Error reading signals from database: {str(read_error)}")

        if not signals:
            logger.warning(f"No trading signals found for portfolio {portfolio_id}")
            raise HTTPException(status_code=404, detail="No trading signals found. Please generate signals first.")

        initial_balance = portfolio['current_balance']
        
        # Step 3: Execute trades
        logger.info("Step 3: Executing trades...")
        execution_results = []
        executed_count = 0
        failed_count = 0

        # Create a temporary portfolio dict for execute_trade compatibility
        portfolio_dict = {
            'balance': portfolio['current_balance'],
            'positions': [],
            'total_invested': portfolio['total_invested'],
            'trade_count': portfolio['trade_count'],
            'total_profit_loss': portfolio['total_profit_loss']
        }

        for signal in signals:
            try:
                # Check if portfolio has sufficient balance
                trade_amount = signal.get('amount', 100)
                if portfolio_dict['balance'] < trade_amount:
                    logger.warning(f"Insufficient balance for signal {signal['id']}: ${portfolio_dict['balance']:.2f} < ${trade_amount}")
                    execution_results.append({
                        "market_id": signal['market_id'],
                        "market_question": signal.get('market_question', 'Unknown'),
                        "action": signal['action'],
                        "amount": signal['amount'],
                        "status": "failed",
                        "reason": f"Insufficient balance: ${portfolio_dict['balance']:.2f} < ${trade_amount}"
                    })
                    failed_count += 1
                    continue

                # Create trade
                trade = {
                    "trade_id": f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{signal['market_id']}_{portfolio_id}",
                    "timestamp": datetime.now().isoformat(),
                    "market_id": signal['market_id'],
                    "market_question": signal['market_question'],
                    "action": signal['action'],
                    "amount": trade_amount,
                    "entry_price": signal['target_price'],
                    "confidence": signal.get('confidence'),
                    "reason": signal['reason'],
                    "status": "open",
                    "event_id": signal.get('event_id'),
                    "event_title": signal.get('event_title'),
                    "event_end_date": signal.get('event_end_date'),
                    "current_pnl": 0.0,
                    "realized_pnl": None
                }

                # Update portfolio balances
                portfolio_dict['balance'] -= trade_amount
                portfolio_dict['total_invested'] += trade_amount
                portfolio_dict['trade_count'] += 1

                # Save trade to database
                insert_trade(trade, portfolio_id=portfolio_id)

                # Add position to database
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
                add_portfolio_position(position, portfolio_id=portfolio_id)

                # Mark signal as executed
                mark_signal_executed(signal['id'], trade['trade_id'], portfolio_id=portfolio_id)

                execution_results.append({
                    "market_id": signal['market_id'],
                    "market_question": signal.get('market_question', 'Unknown'),
                    "action": signal['action'],
                    "amount": signal['amount'],
                    "status": "executed",
                    "reason": "Trade executed successfully"
                })

                executed_count += 1
                logger.info(f"Executed trade {trade['trade_id']} for portfolio {portfolio_id}")

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
                failed_count += 1

        # Step 4: Update portfolio in database
        logger.info("Step 4: Updating portfolio in database...")
        try:
            update_portfolio(portfolio_id, {
                'current_balance': portfolio_dict['balance'],
                'total_invested': portfolio_dict['total_invested'],
                'trade_count': portfolio_dict['trade_count'],
                'last_trade_at': datetime.now()
            })
            logger.info(f"✓ Portfolio {portfolio_id} saved. New balance: ${portfolio_dict['balance']:.2f}")
        except Exception as save_error:
            logger.error(f"✗ Error saving portfolio: {save_error}")
            raise HTTPException(status_code=500, detail=f"Error saving portfolio: {str(save_error)}")
        
        # Step 5: Calculate summary
        logger.info("Step 5: Calculating execution summary...")
        error_count = len([r for r in execution_results if r['status'] == 'error'])
        total_invested = portfolio_dict['total_invested'] - portfolio['total_invested']

        logger.info("=== PAPER TRADING EXECUTION COMPLETED ===")
        logger.info(f"Portfolio {portfolio_id}: Executed {executed_count} trades, {failed_count} failed")

        return {
            "message": "Paper trading execution completed",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "execution_summary": {
                "total_signals": len(signals),
                "executed_trades": executed_count,
                "failed_trades": failed_count,
                "error_trades": error_count,
                "total_invested": total_invested
            },
            "portfolio_update": {
                "initial_balance": initial_balance,
                "final_balance": portfolio_dict['balance'],
                "amount_invested": total_invested,
                "total_trades_count": portfolio_dict['trade_count']
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

@app.post("/portfolios/create")
async def create_portfolio_endpoint(portfolio_data: Dict):
    """
    Create a new portfolio

    Args:
        portfolio_data: Portfolio configuration

    Returns:
        Created portfolio ID

    Example request body:
    {
        "name": "Aggressive Momentum",
        "description": "High-risk momentum strategy",
        "strategy_type": "momentum",
        "initial_balance": 50000.00,
        "strategy_config": {
            "min_confidence": 0.80,
            "market_types": ["crypto", "politics"]
        }
    }
    """
    from src.db.operations import create_portfolio

    try:
        # Validate required fields
        required_fields = ['name', 'strategy_type', 'initial_balance']
        for field in required_fields:
            if field not in portfolio_data:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {field}"
                )

        # Create portfolio
        portfolio_id = create_portfolio(portfolio_data)

        logger.info(f"Created new portfolio: {portfolio_data['name']} (ID: {portfolio_id})")

        return {
            "message": "Portfolio created successfully",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio_data['name'],
            "strategy_type": portfolio_data['strategy_type'],
            "initial_balance": portfolio_data['initial_balance'],
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating portfolio: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating portfolio: {str(e)}")


@app.get("/portfolios/list")
async def list_portfolios(status: Optional[str] = None):
    """
    Get all portfolios, optionally filtered by status

    Args:
        status: Filter by status ('active', 'paused', 'archived'), or None for all

    Returns:
        List of all portfolios
    """
    from src.db.operations import get_all_portfolios

    try:
        portfolios = get_all_portfolios(status=status)

        # Calculate summary statistics
        total_value = sum(
            p['current_balance'] + p.get('total_profit_loss', 0)
            for p in portfolios
        )
        active_count = len([p for p in portfolios if p['status'] == 'active'])

        return {
            "message": f"Retrieved {len(portfolios)} portfolios",
            "portfolios": portfolios,
            "summary": {
                "total_portfolios": len(portfolios),
                "active_portfolios": active_count,
                "total_value_all_portfolios": round(total_value, 2)
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error listing portfolios: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing portfolios: {str(e)}")


@app.get("/portfolios/{portfolio_id}")
async def get_portfolio_by_id(portfolio_id: int):
    """
    Get specific portfolio by ID with full details

    Args:
        portfolio_id: Portfolio ID to retrieve

    Returns:
        Portfolio details including positions
    """
    from src.db.operations import get_portfolio_state, get_portfolio_positions

    try:
        # Get portfolio state
        portfolio = get_portfolio_state(portfolio_id)

        # Get positions for this portfolio
        positions = get_portfolio_positions(portfolio_id, status='open')

        # Try to update P&L with current market data
        try:
            from src.db.operations import get_markets
            market_data = get_markets(filters={'is_filtered': True})
            if market_data:
                # Calculate P&L for this specific portfolio
                portfolio_dict = {
                    'balance': portfolio['current_balance'],
                    'positions': positions,
                    'total_profit_loss': portfolio['total_profit_loss']
                }
                update_portfolio_pnl(portfolio_dict, market_data)
                portfolio['total_profit_loss'] = portfolio_dict['total_profit_loss']

                # Save updated P&L
                from src.db.operations import update_portfolio
                update_portfolio(portfolio_id, {
                    'total_profit_loss': portfolio['total_profit_loss']
                })
        except Exception as pnl_error:
            logger.debug(f"Could not update P&L for portfolio {portfolio_id}: {pnl_error}")

        return {
            "message": "Portfolio retrieved successfully",
            "portfolio": {
                **portfolio,
                'positions': positions
            },
            "summary": {
                "total_value": portfolio['current_balance'] + portfolio.get('total_profit_loss', 0),
                "open_positions": len(positions),
                "total_invested": portfolio['total_invested'],
                "unrealized_pnl": portfolio.get('total_profit_loss', 0)
            },
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting portfolio {portfolio_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting portfolio: {str(e)}")


@app.patch("/portfolios/{portfolio_id}")
async def update_portfolio_endpoint(portfolio_id: int, updates: Dict):
    """
    Update portfolio fields

    Args:
        portfolio_id: Portfolio ID to update
        updates: Dictionary of fields to update

    Returns:
        Updated portfolio confirmation

    Example request body:
    {
        "status": "paused",
        "strategy_config": {
            "min_confidence": 0.85
        }
    }
    """
    from src.db.operations import update_portfolio, get_portfolio_state

    try:
        # Verify portfolio exists
        portfolio = get_portfolio_state(portfolio_id)

        # Validate updates - don't allow changing certain fields
        restricted_fields = ['portfolio_id', 'created_at', 'initial_balance']
        for field in restricted_fields:
            if field in updates:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update restricted field: {field}"
                )

        # Update portfolio
        update_portfolio(portfolio_id, updates)

        # Get updated portfolio
        updated_portfolio = get_portfolio_state(portfolio_id)

        logger.info(f"Updated portfolio {portfolio_id}: {list(updates.keys())}")

        return {
            "message": "Portfolio updated successfully",
            "portfolio_id": portfolio_id,
            "updated_fields": list(updates.keys()),
            "portfolio": updated_portfolio,
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating portfolio {portfolio_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating portfolio: {str(e)}")


@app.post("/portfolios/{portfolio_id}/pause")
async def pause_portfolio_endpoint(portfolio_id: int, reason: Optional[str] = None):
    """
    Pause a portfolio (stop trading but keep data)

    Args:
        portfolio_id: Portfolio ID to pause
        reason: Optional reason for pausing

    Returns:
        Pause confirmation
    """
    from src.db.operations import pause_portfolio, get_portfolio_state

    try:
        # Verify portfolio exists
        portfolio = get_portfolio_state(portfolio_id)

        if portfolio['status'] == 'paused':
            return {
                "message": "Portfolio is already paused",
                "portfolio_id": portfolio_id,
                "portfolio_name": portfolio['name'],
                "status": "paused",
                "timestamp": datetime.now().isoformat()
            }

        # Pause portfolio
        pause_portfolio(portfolio_id, reason)

        logger.info(f"Paused portfolio {portfolio_id}: {reason}")

        return {
            "message": "Portfolio paused successfully",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "reason": reason,
            "status": "paused",
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error pausing portfolio {portfolio_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error pausing portfolio: {str(e)}")


@app.post("/portfolios/{portfolio_id}/resume")
async def resume_portfolio_endpoint(portfolio_id: int):
    """
    Resume a paused portfolio (activate trading)

    Args:
        portfolio_id: Portfolio ID to resume

    Returns:
        Resume confirmation
    """
    from src.db.operations import update_portfolio, get_portfolio_state

    try:
        # Verify portfolio exists
        portfolio = get_portfolio_state(portfolio_id)

        if portfolio['status'] == 'active':
            return {
                "message": "Portfolio is already active",
                "portfolio_id": portfolio_id,
                "portfolio_name": portfolio['name'],
                "status": "active",
                "timestamp": datetime.now().isoformat()
            }

        # Resume portfolio
        update_portfolio(portfolio_id, {'status': 'active'})

        logger.info(f"Resumed portfolio {portfolio_id}")

        return {
            "message": "Portfolio resumed successfully",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "status": "active",
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error resuming portfolio {portfolio_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error resuming portfolio: {str(e)}")


@app.get("/paper-trading/portfolio")
async def get_portfolio(portfolio_id: Optional[int] = None):
    """
    Get current portfolio state from database

    Args:
        portfolio_id: Portfolio ID (optional, defaults to first active portfolio)

    Returns:
        Current portfolio information with positions
    """
    from src.db.operations import get_portfolio_state, get_portfolio_positions, update_portfolio

    try:
        # Get portfolio state from database
        portfolio = get_portfolio_state(portfolio_id)
        portfolio_id = portfolio['portfolio_id']  # Use actual ID in case None was passed

        # Get positions for this portfolio
        positions = get_portfolio_positions(portfolio_id, status='open')

        # Try to update P&L with current market data from database
        try:
            from src.db.operations import get_markets
            market_data = get_markets(filters={'is_filtered': True})
            if market_data:
                # Calculate P&L for this specific portfolio
                portfolio_dict = {
                    'balance': portfolio['current_balance'],
                    'positions': positions,
                    'total_profit_loss': portfolio['total_profit_loss']
                }
                update_portfolio_pnl(portfolio_dict, market_data)
                portfolio['total_profit_loss'] = portfolio_dict['total_profit_loss']

                # Save updated P&L
                update_portfolio(portfolio_id, {
                    'total_profit_loss': portfolio['total_profit_loss'],
                    'last_price_update': datetime.now()
                })
        except Exception as pnl_error:
            logger.debug(f"Could not update P&L for portfolio {portfolio_id}: {pnl_error}")

        return {
            "message": "Portfolio retrieved from database",
            "portfolio_id": portfolio_id,
            "portfolio": {
                **portfolio,
                'positions': positions
            },
            "summary": {
                "total_value": portfolio['current_balance'] + portfolio.get('total_profit_loss', 0),
                "open_positions": len(positions),
                "total_invested": portfolio['total_invested'],
                "unrealized_pnl": portfolio.get('total_profit_loss', 0)
            },
            "timestamp": datetime.now().isoformat()
        }

    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting portfolio: {str(e)}")

@app.get("/paper-trading/trades-history")
async def get_trades_history(portfolio_id: Optional[int] = None, limit: Optional[int] = None):
    """
    Get complete trading history from database

    Args:
        portfolio_id: Portfolio ID (optional, defaults to first active portfolio)
        limit: Maximum number of trades to return (optional)

    Returns:
        All executed trades history for the specified portfolio
    """
    from src.db.operations import get_trades, get_portfolio_state

    try:
        # Get portfolio info if portfolio_id specified
        portfolio_name = None
        if portfolio_id is not None:
            try:
                portfolio = get_portfolio_state(portfolio_id)
                portfolio_name = portfolio['name']
            except ValueError:
                raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

        # Get trades for this portfolio
        trades_history = get_trades(portfolio_id=portfolio_id, limit=limit)

        response = {
            "message": "Trading history retrieved from database",
            "trades_count": len(trades_history),
            "trades": trades_history,
            "timestamp": datetime.now().isoformat()
        }

        if portfolio_id is not None:
            response["portfolio_id"] = portfolio_id
            response["portfolio_name"] = portfolio_name

        if limit:
            response["limit"] = limit

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trades history from database: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting trades history: {str(e)}")

@app.get("/price-updater/update")
async def update_portfolio_prices(portfolio_id: Optional[int] = None):
    """
    Manually trigger price update for one portfolio or all active portfolios

    Args:
        portfolio_id: Portfolio ID to update (None = update all active portfolios)

    Returns:
        Price update result
    """
    try:
        updater = get_price_updater()
        if not updater:
            raise HTTPException(status_code=503, detail="Price updater not running")

        if portfolio_id is not None:
            # Update specific portfolio
            from src.db.operations import get_portfolio_state
            try:
                portfolio = get_portfolio_state(portfolio_id)
                logger.info(f"Manual price update triggered for portfolio {portfolio_id}: {portfolio['name']}")
            except ValueError:
                raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

            updater.update_open_positions_prices(portfolio_id=portfolio_id)

            # Get updated portfolio
            portfolio = get_portfolio_state(portfolio_id)

            return {
                "message": f"Price update completed for portfolio {portfolio_id}",
                "portfolio_id": portfolio_id,
                "portfolio_name": portfolio['name'],
                "portfolio_pnl": portfolio.get('total_profit_loss', 0),
                "last_price_update": portfolio.get('last_price_update'),
                "timestamp": datetime.now().isoformat()
            }
        else:
            # Update all active portfolios
            from src.db.operations import get_all_portfolios
            portfolios = get_all_portfolios(status='active')

            logger.info(f"Manual price update triggered for {len(portfolios)} active portfolios")
            updater.update_open_positions_prices()  # Updates all

            # Get summary of all portfolios
            portfolio_summaries = []
            for p in portfolios:
                portfolio_summaries.append({
                    'portfolio_id': p['portfolio_id'],
                    'name': p['name'],
                    'total_pnl': p.get('total_profit_loss', 0)
                })

            return {
                "message": f"Price update completed for {len(portfolios)} active portfolios",
                "portfolios_updated": len(portfolios),
                "portfolio_summaries": portfolio_summaries,
                "timestamp": datetime.now().isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating prices: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating prices: {str(e)}")


@app.get("/paper-trading/update-prices")
async def update_prices(portfolio_id: Optional[int] = None):
    """
    DEPRECATED: Use /price-updater/update instead
    Manually trigger price update for open positions in a portfolio

    Args:
        portfolio_id: Portfolio ID (optional, defaults to first active portfolio)

    Returns:
        Price update result
    """
    logger.warning("DEPRECATED: /paper-trading/update-prices is deprecated, use /price-updater/update instead")
    return await update_portfolio_prices(portfolio_id=portfolio_id)

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