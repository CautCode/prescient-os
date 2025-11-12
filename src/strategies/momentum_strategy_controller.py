"""
Momentum Strategy Controller

Strategy: Buy markets with >50% probability on the most likely outcome
This is the "follow the momentum" strategy - bet on what the market thinks will happen.

Filtering Criteria:
- Moderate to high liquidity for easy entry/exit
- Moderate market conviction (0.50-0.65) to find momentum opportunities
- Balanced risk/reward profile

Port: 8002
"""

from fastapi import FastAPI, HTTPException
from typing import Dict, List
import os
import logging
from datetime import datetime

# Set up logging
log_level = getattr(logging, os.getenv('PYTHON_LOG_LEVEL', 'INFO'))
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Momentum Strategy Controller", version="1.0.0")

# Strategy metadata
STRATEGY_INFO = {
    "name": "Momentum Strategy",
    "description": "Buy markets with >50% probability on the most likely outcome",
    "strategy_type": "momentum",
    "version": "1.0.0",
    "default_config": {
        # Event filtering
        "event_min_liquidity": 10000,
        "event_min_volume": 50000,
        "event_min_volume_24hr": None,
        "event_max_days_until_end": None,
        "event_min_days_until_end": None,

        # Market filtering
        "market_min_liquidity": 10000,
        "market_min_volume": 50000,
        "market_min_volume_24hr": None,
        "market_min_conviction": 0.50,
        "market_max_conviction": 0.60,

        # Strategy-specific parameters
        "min_confidence": 0.75,  # Minimum confidence to generate signal
        "max_positions": 10,      # Maximum number of positions to take
        "trade_amount": 100       # Amount to invest per trade
    }
}


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Momentum Strategy Controller is running",
        "strategy": STRATEGY_INFO["name"],
        "version": STRATEGY_INFO["version"],
        "timestamp": datetime.now().isoformat()
    }


@app.post("/strategy/execute-full-cycle")
async def execute_full_strategy_cycle(portfolio_id: int):
    """
    Execute complete momentum strategy cycle for a portfolio

    This endpoint handles:
    1. Loading portfolio and merging strategy_config with defaults
    2. Exporting events from events controller
    3. Filtering events with strategy-specific criteria
    4. Filtering markets with strategy-specific criteria
    5. Analyzing markets with momentum strategy logic
    6. Generating trading signals
    7. Saving signals to database

    Args:
        portfolio_id: Portfolio ID to execute strategy for

    Returns:
        Strategy execution results with signals generated
    """
    from src.db.operations import get_portfolio_state, get_markets, insert_signals

    try:
        logger.info(f"=== MOMENTUM STRATEGY: Starting cycle for portfolio {portfolio_id} ===")

        # Step 1: Load portfolio and get strategy config
        logger.info("Step 1: Loading portfolio and strategy configuration...")
        try:
            portfolio = get_portfolio_state(portfolio_id)
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))

        # Verify portfolio strategy type matches
        if portfolio['strategy_type'] != 'momentum':
            logger.warning(
                f"Portfolio {portfolio_id} has strategy_type='{portfolio['strategy_type']}' "
                f"but momentum controller was called. Proceeding anyway."
            )

        # Merge portfolio config with defaults
        portfolio_config = portfolio.get('strategy_config', {})
        strategy_config = {**STRATEGY_INFO["default_config"], **portfolio_config}

        logger.info(f"Portfolio: {portfolio['name']}")
        logger.info(f"Strategy config: {strategy_config}")

        # Step 2: Export events
        logger.info("Step 2: Exporting all active events...")
        import requests
        try:
            events_response = requests.get(
                "http://localhost:8000/events/export-all-active-events-db",
                timeout=300
            )
            events_response.raise_for_status()
            events_result = events_response.json()
            logger.info(f"✓ Exported {events_result.get('total_events', 0)} events")
        except Exception as events_error:
            logger.error(f"✗ Error exporting events: {events_error}")
            raise HTTPException(status_code=500, detail=f"Error exporting events: {str(events_error)}")

        # Step 3: Filter events with strategy-specific criteria
        logger.info("Step 3: Filtering events with momentum strategy criteria...")
        try:
            event_params = {
                "min_liquidity": strategy_config["event_min_liquidity"],
                "min_volume": strategy_config["event_min_volume"],
                "min_volume_24hr": strategy_config["event_min_volume_24hr"],
                "max_days_until_end": strategy_config["event_max_days_until_end"],
                "min_days_until_end": strategy_config["event_min_days_until_end"]
            }
            # Remove None values
            event_params = {k: v for k, v in event_params.items() if v is not None}

            filter_events_response = requests.get(
                "http://localhost:8000/events/filter-trading-candidates-db",
                params=event_params,
                timeout=300
            )
            filter_events_response.raise_for_status()
            filter_events_result = filter_events_response.json()
            logger.info(f"✓ Filtered {filter_events_result.get('total_candidates', 0)} event candidates")
        except Exception as filter_error:
            logger.error(f"✗ Error filtering events: {filter_error}")
            raise HTTPException(status_code=500, detail=f"Error filtering events: {str(filter_error)}")

        # Step 4: Filter markets with strategy-specific criteria
        logger.info("Step 4: Filtering markets with momentum strategy criteria...")
        try:
            market_params = {
                "min_liquidity": strategy_config["market_min_liquidity"],
                "min_volume": strategy_config["market_min_volume"],
                "min_volume_24hr": strategy_config["market_min_volume_24hr"],
                "min_market_conviction": strategy_config["market_min_conviction"],
                "max_market_conviction": strategy_config["market_max_conviction"]
            }
            # Remove None values
            market_params = {k: v for k, v in market_params.items() if v is not None}

            filter_markets_response = requests.get(
                "http://localhost:8001/markets/export-filtered-markets-db",
                params=market_params,
                timeout=300
            )
            filter_markets_response.raise_for_status()
            filter_markets_result = filter_markets_response.json()
            logger.info(f"✓ Filtered {filter_markets_result.get('filtered_markets', 0)} market candidates")
        except Exception as market_error:
            logger.error(f"✗ Error filtering markets: {market_error}")
            raise HTTPException(status_code=500, detail=f"Error filtering markets: {str(market_error)}")

        # Step 5: Load filtered markets from database
        logger.info("Step 5: Loading filtered markets from database...")
        markets_data = get_markets({'is_filtered': True})

        if not markets_data:
            logger.warning("No markets found after filtering")
            return {
                "message": "No markets available for momentum strategy",
                "portfolio_id": portfolio_id,
                "portfolio_name": portfolio['name'],
                "strategy_type": "momentum",
                "signals_generated": 0,
                "markets_analyzed": 0,
                "strategy_config_used": strategy_config,
                "timestamp": datetime.now().isoformat()
            }

        logger.info(f"✓ Loaded {len(markets_data)} markets from database")

        # Step 6: Apply momentum strategy logic
        logger.info(f"Step 6: Analyzing {len(markets_data)} markets with momentum strategy...")
        signals = generate_momentum_signals(
            markets_data,
            min_confidence=strategy_config["min_confidence"],
            max_positions=strategy_config["max_positions"],
            trade_amount=strategy_config["trade_amount"]
        )

        logger.info(f"✓ Generated {len(signals)} signals")

        # Step 7: Save signals to database
        if signals:
            logger.info("Step 7: Saving signals to database...")
            try:
                prepared_signals = prepare_signals_for_db(signals)
                inserted_ids = insert_signals(
                    prepared_signals,
                    portfolio_id=portfolio_id,
                    strategy_type="momentum"
                )
                logger.info(f"✓ Saved {len(inserted_ids)} signals to database")
            except Exception as db_error:
                logger.error(f"✗ Error saving signals to database: {db_error}")
                raise HTTPException(status_code=500, detail=f"Error saving signals: {str(db_error)}")
        else:
            logger.info("No signals to save")

        logger.info(f"=== MOMENTUM STRATEGY: Completed cycle for portfolio {portfolio_id} ===")

        return {
            "message": "Momentum strategy cycle completed",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "strategy_type": "momentum",
            "signals_generated": len(signals),
            "markets_analyzed": len(markets_data),
            "events_filtered": filter_events_result.get('total_candidates', 0),
            "markets_filtered": filter_markets_result.get('filtered_markets', 0),
            "strategy_config_used": strategy_config,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in momentum strategy cycle: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def generate_momentum_signals(
    markets_data: List[Dict],
    min_confidence: float,
    max_positions: int,
    trade_amount: float
) -> List[Dict]:
    """
    Generate signals using momentum strategy logic (>50% buy most likely outcome)

    Strategy Logic:
    - Buy YES if yes_price > 0.50 and yes_price >= no_price
    - Buy NO if no_price > 0.50 and no_price > yes_price
    - Confidence = price - 0.50 (how much above 50%)
    - Only generate signals with confidence >= threshold

    Args:
        markets_data: List of filtered market dictionaries
        min_confidence: Minimum confidence threshold (e.g., 0.75 means price must be >= 0.75)
        max_positions: Maximum number of signals to generate
        trade_amount: Amount to invest per trade

    Returns:
        List of signal dictionaries sorted by confidence (highest first)
    """
    logger.info(f"=== GENERATING MOMENTUM SIGNALS ===")
    logger.info(f"Input: {len(markets_data)} markets, min_confidence={min_confidence}, max_positions={max_positions}")

    signals = []
    current_time = datetime.now()

    for market in markets_data:
        try:
            # Parse market data
            market_id = market.get('id')
            market_question = market.get('question', 'Unknown Question')

            # Get prices
            yes_price = float(market.get('yes_price', 0))
            no_price = float(market.get('no_price', 0))

            # Momentum strategy: Buy if either price > 50%
            if yes_price > 0.50 or no_price > 0.50:
                if yes_price >= no_price:
                    # YES is the more likely outcome
                    action = 'buy_yes'
                    target_price = yes_price
                    confidence = yes_price - 0.50  # How much above 50%
                    reason = f"Momentum: YES price {yes_price:.3f} > 0.50, buying YES at {yes_price:.3f}"
                else:
                    # NO is the more likely outcome
                    action = 'buy_no'
                    target_price = no_price
                    confidence = no_price - 0.50
                    reason = f"Momentum: NO price {no_price:.3f} > 0.50, buying NO at {no_price:.3f}"

                # Check confidence threshold
                # min_confidence is the target price (e.g., 0.75)
                # So we need target_price >= min_confidence
                if target_price < min_confidence:
                    logger.debug(
                        f"Skipping market {market_id}: target_price {target_price:.3f} < "
                        f"min_confidence {min_confidence}"
                    )
                    continue

                # Create trading signal
                signal = {
                    'timestamp': current_time.isoformat(),
                    'market_id': market_id,
                    'market_question': market_question,
                    'action': action,
                    'target_price': target_price,
                    'amount': trade_amount,
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

                # Limit positions
                if len(signals) >= max_positions:
                    logger.info(f"Reached max_positions limit ({max_positions}), stopping signal generation")
                    break

            else:
                logger.debug(
                    f"Skipping market {market_id}: No price > 0.50 "
                    f"(YES: {yes_price:.3f}, NO: {no_price:.3f})"
                )

        except Exception as market_error:
            logger.warning(f"Error processing market {market.get('id', 'unknown')}: {market_error}")
            continue

    # Sort signals by confidence (highest first) for best trading opportunities
    try:
        signals.sort(key=lambda x: x['confidence'], reverse=True)
    except Exception as sort_error:
        logger.warning(f"Error sorting signals by confidence: {sort_error}")

    # Limit to max_positions
    signals = signals[:max_positions]

    logger.info(f"=== SIGNAL GENERATION COMPLETE ===")
    logger.info(f"Generated {len(signals)} signals from {len(markets_data)} markets")

    return signals


def prepare_signals_for_db(signals: List[Dict]) -> List[Dict]:
    """
    Prepare signals for database insertion
    Converts timestamps and ensures all required fields are present

    Args:
        signals: List of raw signal dictionaries

    Returns:
        List of prepared signal dictionaries
    """
    prepared = []

    for signal in signals:
        # Convert timestamp to datetime if needed
        ts = signal.get('timestamp')
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except Exception:
                ts = datetime.now()
        elif ts is None:
            ts = datetime.now()

        # Handle event_end_date
        eed = signal.get('event_end_date')

        prepared.append({
            'timestamp': ts,
            'market_id': signal.get('market_id'),
            'market_question': signal.get('market_question'),
            'action': signal.get('action'),
            'target_price': float(signal.get('target_price')) if signal.get('target_price') is not None else None,
            'amount': float(signal.get('amount')) if signal.get('amount') is not None else None,
            'confidence': float(signal.get('confidence')) if signal.get('confidence') is not None else None,
            'reason': signal.get('reason'),
            'yes_price': float(signal.get('yes_price')) if signal.get('yes_price') is not None else None,
            'no_price': float(signal.get('no_price')) if signal.get('no_price') is not None else None,
            'market_liquidity': float(signal.get('market_liquidity')) if signal.get('market_liquidity') is not None else None,
            'market_volume': float(signal.get('market_volume')) if signal.get('market_volume') is not None else None,
            'event_id': signal.get('event_id'),
            'event_title': signal.get('event_title'),
            'event_end_date': eed,
            'executed': False,
            'executed_at': None,
            'trade_id': None
        })

    return prepared


@app.get("/strategy/info")
async def get_strategy_info():
    """
    Get momentum strategy metadata

    Returns:
        Strategy information including name, description, type, and default configuration
    """
    return STRATEGY_INFO


@app.post("/strategy/validate-config")
async def validate_strategy_config(config: Dict):
    """
    Validate momentum strategy configuration

    Args:
        config: Strategy configuration dictionary to validate

    Returns:
        Validation result with valid flag and list of errors
    """
    required_fields = [
        "event_min_liquidity",
        "market_min_liquidity",
        "min_confidence",
        "trade_amount"
    ]

    errors = []
    missing = [f for f in required_fields if f not in config]

    if missing:
        errors.extend([f"Missing required field: {f}" for f in missing])

    # Validate numeric ranges
    if "min_confidence" in config:
        if not (0.5 <= config["min_confidence"] <= 1.0):
            errors.append("min_confidence must be between 0.5 and 1.0")

    if "trade_amount" in config:
        if config["trade_amount"] <= 0:
            errors.append("trade_amount must be positive")

    if "max_positions" in config:
        if config["max_positions"] <= 0:
            errors.append("max_positions must be positive")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


@app.get("/strategy/status")
async def get_strategy_status():
    """
    Get status of momentum strategy controller

    Returns:
        Status information
    """
    return {
        "strategy": STRATEGY_INFO["name"],
        "strategy_type": STRATEGY_INFO["strategy_type"],
        "version": STRATEGY_INFO["version"],
        "status": "online",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
    # uvicorn src.strategies.momentum_strategy_controller:app --reload --port 8002
