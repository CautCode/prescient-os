# Trading Strategy Controller - Analyzes market data and generates trading signals using >50% strategy
# Main functions: generate_signals(), generate_trading_signals(), get_current_signals()
# Used by: trading_controller.py for signal generation based on market probability analysis

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

app = FastAPI(title="Polymarket Trading Strategy API", version="1.0.0")

# Helper Functions
def ensure_data_directories():
    """
    Create necessary data directories if they don't exist
    """
    os.makedirs("data/trades", exist_ok=True)

def generate_trading_signals(market_data: List[Dict]) -> List[Dict]:
    """
    Generate trading signals based on >50% buy-most-likely strategy

    Args:
        market_data: List of market objects with pricing data

    Returns:
        List of trading signal objects
    """
    logger.info(f"=== ENTERING GENERATE_TRADING_SIGNALS ===")
    logger.info(f"Input markets count: {len(market_data)}")

    signals = []
    current_time = datetime.now()

    for market in market_data:
        try:
            market_id = market.get('id')
            market_question = market.get('question', 'Unknown Question')

            # Parse outcome prices
            outcome_prices_str = market.get('outcomePrices', '[]')
            try:
                import ast
                outcome_prices = ast.literal_eval(outcome_prices_str)
                if not outcome_prices or len(outcome_prices) < 2:
                    logger.debug(f"Skipping market {market_id}: Invalid outcome prices")
                    continue

                yes_price = float(outcome_prices[0])
                no_price = float(outcome_prices[1])

            except Exception as price_error:
                logger.debug(f"Error parsing prices for market {market_id}: {price_error}")
                continue

            # Apply >50% buy-most-likely strategy
            if yes_price > 0.50 or no_price > 0.50:
                if yes_price >= no_price:
                    # YES is the more likely (>0.5) outcome
                    action = 'buy_yes'
                    target_price = yes_price
                    confidence = yes_price - 0.50  # How much above 50%
                    reason = f"YES price {yes_price:.3f} > 0.50, buying YES at {yes_price:.3f}"
                else:
                    # NO is the more likely (>0.5) outcome
                    action = 'buy_no'
                    target_price = no_price
                    confidence = no_price - 0.50
                    reason = f"NO price {no_price:.3f} > 0.50, buying NO at {no_price:.3f}"
            else:
                # Neither price > 50%, skip this market
                logger.debug(
                    f"Skipping market {market_id}: No price > 0.50 (YES: {yes_price:.3f}, NO: {no_price:.3f})")
                continue

            # Create trading signal
            signal = {
                'timestamp': current_time.isoformat(),
                'market_id': market_id,
                'market_question': market_question,
                'action': action,
                'target_price': target_price,
                'amount': 100,  # Fixed $100 trades as per MVP spec
                'confidence': round(confidence, 4),
                'reason': reason,
                'yes_price': yes_price,
                'no_price': no_price,
                'market_liquidity': float(market.get('liquidity', 0)),
                'market_volume': float(market.get('volume', 0)),
                'event_id': market.get('event_id'),
                'event_title': market.get('event_title'),
                'event_end_date': market.get('event_end_date')
            }

            signals.append(signal)
            logger.debug(f"Generated signal for market {market_id}: {action} at {target_price:.3f}")

        except Exception as market_error:
            logger.warning(f"Error processing market {market.get('id', 'unknown')}: {market_error}")
            continue

    # Sort signals by confidence (highest first) for best trading opportunities
    try:
        signals.sort(key=lambda x: x['confidence'], reverse=True)
    except Exception as sort_error:
        logger.warning(f"Error sorting signals by confidence: {sort_error}")

    logger.info(f"=== EXITING GENERATE_TRADING_SIGNALS ===")
    logger.info(f"Generated {len(signals)} trading signals from {len(market_data)} markets")

    return signals

# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Polymarket Trading Strategy API is running", "timestamp": datetime.now().isoformat()}

@app.get("/strategy/generate-signals")
async def generate_signals():
    """
    Analyze markets and generate trading signals (Phase 4: Reads markets from database)

    Returns:
        JSON response with generated signals and summary
    """
    from src.db.operations import get_markets

    try:
        logger.info("=== STARTING TRADING SIGNAL GENERATION ===")

        # Ensure directories exist (still needed for saving signals to JSON)
        ensure_data_directories()

        # Step 1: Read filtered markets from DATABASE (not JSON)
        logger.info("Step 1: Loading filtered markets from database...")
        markets_data = get_markets({'is_filtered': True})

        if not markets_data:
            raise HTTPException(status_code=404,
                detail="No markets data found in database. Please filter markets first.")

        logger.info(f"Successfully loaded {len(markets_data)} markets from database")
        
        # Step 2: Generate trading signals
        logger.info("Step 2: Generating trading signals...")
        try:
            signals = generate_trading_signals(markets_data)
            logger.info(f"✓ Successfully generated {len(signals)} trading signals")
        except Exception as signal_error:
            logger.error(f"✗ Error generating signals: {signal_error}")
            import traceback
            logger.error(f"Signal generation traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Error generating signals: {str(signal_error)}")
        
        # Step 3: Save signals to current_signals.json
        logger.info("Step 3: Saving trading signals...")
        signals_path = os.path.join("data", "trades", "current_signals.json")
        
        try:
            with open(signals_path, "w", encoding="utf-8") as f:
                json.dump(signals, f, indent=2, ensure_ascii=False)
            logger.info(f"✓ Successfully saved {len(signals)} signals to: {signals_path}")
        except Exception as save_error:
            logger.error(f"✗ Error saving signals: {save_error}")
            raise HTTPException(status_code=500, detail=f"Error saving signals: {str(save_error)}")
        
        # Step 4: Calculate summary statistics
        logger.info("Step 4: Calculating summary statistics...")
        try:
            total_signals = len(signals)
            buy_yes_count = len([s for s in signals if s['action'] == 'buy_yes'])
            buy_no_count = len([s for s in signals if s['action'] == 'buy_no'])
            
            if total_signals > 0:
                avg_confidence = sum(s['confidence'] for s in signals) / total_signals
                total_amount = sum(s['amount'] for s in signals)
                avg_target_price = sum(s['target_price'] for s in signals) / total_signals
                logger.info(f"✓ Stats - avg_confidence: {avg_confidence:.4f}, total_amount: ${total_amount}, avg_price: {avg_target_price:.4f}")
            else:
                avg_confidence = total_amount = avg_target_price = 0
                
        except Exception as stats_error:
            logger.error(f"✗ Error calculating stats: {stats_error}")
            avg_confidence = total_amount = avg_target_price = 0
            buy_yes_count = buy_no_count = 0
        
        logger.info("=== TRADING SIGNAL GENERATION COMPLETED SUCCESSFULLY ===")
        
        return {
            "message": "Trading signals generated successfully",
            "source_file": markets_path,
            "output_file": signals_path,
            "total_markets_analyzed": len(markets_data),
            "total_signals_generated": total_signals,
            "signal_breakdown": {
                "buy_yes_signals": buy_yes_count,
                "buy_no_signals": buy_no_count
            },
            "summary_stats": {
                "avg_confidence": round(avg_confidence, 4) if avg_confidence else None,
                "total_investment_amount": total_amount,
                "avg_target_price": round(avg_target_price, 4) if avg_target_price else None
            },
            "strategy": ">50% buy strategy - bet on the most likely outcome",
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR IN SIGNAL GENERATION ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/strategy/current-signals")
async def get_current_signals():
    """
    Get latest generated trading signals
    
    Returns:
        Current trading signals data
    """
    try:
        signals_path = os.path.join("data", "trades", "current_signals.json")
        
        if not os.path.exists(signals_path):
            raise HTTPException(status_code=404, detail="No trading signals found. Please generate signals first.")
        
        with open(signals_path, "r", encoding="utf-8") as f:
            signals_data = json.load(f)
        
        return {
            "message": "Current trading signals retrieved",
            "signals_count": len(signals_data),
            "signals": signals_data,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading trading signals: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading trading signals: {str(e)}")

@app.get("/strategy/status")
async def get_strategy_status():
    """
    Get status of trading strategy system
    
    Returns:
        Status information about signals and strategy
    """
    try:
        status = {
            "timestamp": datetime.now().isoformat(),
            "signals_exist": False,
            "signals_count": 0,
            "signals_last_generated": None,
            "strategy_type": ">50% buy strategy"
        }
        
        # Check current signals
        signals_path = os.path.join("data", "trades", "current_signals.json")
        if os.path.exists(signals_path):
            status["signals_exist"] = True
            status["signals_last_generated"] = datetime.fromtimestamp(os.path.getmtime(signals_path)).isoformat()
            
            try:
                with open(signals_path, "r", encoding="utf-8") as f:
                    signals_data = json.load(f)
                    status["signals_count"] = len(signals_data)
                    
                    # Add signal breakdown
                    if signals_data:
                        buy_yes = len([s for s in signals_data if s.get('action') == 'buy_yes'])
                        buy_no = len([s for s in signals_data if s.get('action') == 'buy_no'])
                        status["signal_breakdown"] = {
                            "buy_yes_signals": buy_yes,
                            "buy_no_signals": buy_no
                        }
            except:
                pass
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting strategy status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting strategy status: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
    # uvicorn src.trading_strategy_controller:app --reload