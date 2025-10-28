# Price Updater - Background thread that periodically fetches current market prices and updates portfolio P&L
# Main functions: start_price_updater(), stop_price_updater(), update_open_positions_prices()
# Used by: paper_trading_controller.py to keep portfolio P&L accurate between trading cycles
# Updated for PostgreSQL database integration (Phase 1+)

import time
import threading
import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Set up logging
log_level = getattr(logging, os.getenv('PYTHON_LOG_LEVEL', 'INFO'))
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

class PriceUpdater:
    """Background thread that periodically updates prices for open positions"""

    def __init__(self, update_interval=300):  # 5 minutes default
        self.update_interval = update_interval
        self.running = False
        self.thread = None
        logger.info(f"PriceUpdater initialized with {update_interval}s interval")

    def start(self):
        """Start the background price update thread"""
        if self.running:
            logger.warning("Price updater already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        logger.info(f"✓ Price updater started (interval: {self.update_interval}s)")

    def stop(self):
        """Stop the background price update thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Price updater stopped")

    def _update_loop(self):
        """Main update loop - runs in background thread"""
        while self.running:
            try:
                self.update_open_positions_prices()
            except Exception as e:
                logger.error(f"Error in price update loop: {e}")
                import traceback
                logger.error(traceback.format_exc())

            # Sleep in 1-second intervals so we can stop quickly
            for _ in range(self.update_interval):
                if not self.running:
                    break
                time.sleep(1)

    def update_open_positions_prices(self):
        """Fetch current prices for all markets with open positions and update P&L"""
        try:
            # Step 1: Load portfolio from database to get open positions
            from src.db.operations import get_portfolio_positions, upsert_portfolio_state, get_portfolio_state, insert_market_snapshot
            
            # Get open positions from database
            open_positions = get_portfolio_positions(status='open')

            if not open_positions:
                logger.debug("No open positions, skipping price update")
                return

            # Step 2: Extract unique market IDs from open positions
            market_ids = list(set(p['market_id'] for p in open_positions))
            logger.info(f"Updating prices for {len(market_ids)} markets with open positions...")

            # Step 3: Fetch current prices from Polymarket API
            current_prices = self._fetch_market_prices(market_ids)

            if not current_prices:
                logger.warning("No prices fetched, skipping P&L update")
                return

            # Step 4: Update P&L and save to database
            self._update_portfolio_pnl_in_db(open_positions, current_prices)

            # Step 5: Store market snapshots for time-series data
            for market_id, price_data in current_prices.items():
                insert_market_snapshot(market_id, price_data)

            logger.info(f"✓ Updated portfolio P&L and stored market snapshots")

        except Exception as e:
            logger.error(f"Error updating open positions prices: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _fetch_market_prices(self, market_ids: List[str]) -> Dict[str, Dict]:
        """Fetch current prices for given market IDs from Polymarket API"""
        prices = {}

        try:
            # Use batched API request (same as market_controller.py)
            BASE_URL = "https://gamma-api.polymarket.com"

            # Fetch in batches of 10
            batch_size = 10
            for i in range(0, len(market_ids), batch_size):
                batch = market_ids[i:i+batch_size]

                url = f"{BASE_URL}/markets"
                params = [f"id={mid}" for mid in batch]
                if params:
                    url += "?" + "&".join(params)

                logger.debug(f"Fetching batch {i//batch_size + 1}: {url}")
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                markets = response.json()

                # Extract prices from response
                for market in markets:
                    market_id = market.get('id')
                    outcome_prices_str = market.get('outcomePrices', '[]')

                    try:
                        import ast
                        outcome_prices = ast.literal_eval(outcome_prices_str)
                        if len(outcome_prices) >= 2:
                            prices[market_id] = {
                                'yes_price': float(outcome_prices[0]),
                                'no_price': float(outcome_prices[1]),
                                'liquidity': float(market.get('liquidity', 0)),
                                'volume': float(market.get('volume', 0)),
                                'updated_at': datetime.now().isoformat()
                            }
                            logger.debug(f"  {market_id}: YES={prices[market_id]['yes_price']:.4f}, NO={prices[market_id]['no_price']:.4f}")
                    except Exception as parse_error:
                        logger.warning(f"Error parsing prices for market {market_id}: {parse_error}")

                # Rate limiting
                time.sleep(0.5)

            logger.info(f"✓ Fetched prices for {len(prices)}/{len(market_ids)} markets")
            return prices

        except Exception as e:
            logger.error(f"Error fetching market prices: {e}")
            return {}

    def _update_portfolio_pnl_in_db(self, open_positions: List[Dict], current_prices: Dict[str, Dict]):
        """
        Update portfolio P&L in database based on current market prices
        """
        try:
            from src.db.operations import update_portfolio_position, get_portfolio_state, upsert_portfolio_state
            
            total_pnl = 0.0
            updated_positions = 0

            for position in open_positions:
                market_id = position.get('market_id')
                if market_id not in current_prices:
                    logger.warning(f"No current price for market {market_id}")
                    continue

                # Get current price based on action
                action = position.get('action')
                entry_price = position.get('entry_price', 0)
                amount = position.get('amount', 0)

                price_data = current_prices[market_id]

                if action == 'buy_yes':
                    current_price = price_data['yes_price']
                elif action == 'buy_no':
                    current_price = price_data['no_price']
                else:
                    logger.warning(f"Unknown action: {action}")
                    continue

                # Calculate P&L
                # P&L = (current_price - entry_price) * amount
                position_pnl = (current_price - entry_price) * amount
                position_pnl_rounded = round(position_pnl, 2)

                # Update position in database
                update_portfolio_position(
                    position['trade_id'], 
                    {'current_pnl': position_pnl_rounded}
                )
                
                total_pnl += position_pnl
                updated_positions += 1

                logger.debug(f"  Position {market_id}: entry={entry_price:.4f}, current={current_price:.4f}, P&L=${position_pnl:.2f}")

            # Update portfolio state with new total P&L
            portfolio_state = get_portfolio_state()
            portfolio_state['total_profit_loss'] = round(total_pnl, 2)
            portfolio_state['last_updated'] = datetime.now()
            
            upsert_portfolio_state(portfolio_state)

            logger.info(f"Updated P&L for {updated_positions} open positions in database")

        except Exception as e:
            logger.error(f"Error updating portfolio P&L in database: {e}")
            import traceback
            logger.error(traceback.format_exc())


# Global instance
_price_updater = None

def start_price_updater(update_interval=300):
    """Start the global price updater"""
    global _price_updater
    if _price_updater is None:
        _price_updater = PriceUpdater(update_interval)
    _price_updater.start()
    return _price_updater

def stop_price_updater():
    """Stop the global price updater"""
    global _price_updater
    if _price_updater:
        _price_updater.stop()
        _price_updater = None

def get_price_updater():
    """Get the global price updater instance"""
    return _price_updater
