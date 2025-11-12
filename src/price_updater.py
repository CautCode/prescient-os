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

    def update_open_positions_prices(self, portfolio_id: Optional[int] = None):
        """
        Fetch current prices for all markets with open positions and update P&L

        Args:
            portfolio_id: Update specific portfolio (None = update all active portfolios)
        """
        try:
            from src.db.operations import (
                get_all_portfolios, get_portfolio_positions,
                update_portfolio, insert_market_snapshot
            )

            # Determine which portfolios to update
            if portfolio_id is not None:
                # Update specific portfolio
                portfolios = [{'portfolio_id': portfolio_id}]
                logger.info(f"Updating prices for portfolio {portfolio_id}...")
            else:
                # Update all active portfolios
                portfolios = get_all_portfolios(status='active')
                logger.info(f"Updating prices for {len(portfolios)} active portfolios...")

            if not portfolios:
                logger.warning("No active portfolios found, skipping price update")
                return

            # Collect all unique market IDs across all portfolios to minimize API calls
            all_market_ids = set()
            portfolio_positions_map = {}

            for portfolio in portfolios:
                pid = portfolio['portfolio_id']
                open_positions = get_portfolio_positions(portfolio_id=pid, status='open')

                if open_positions:
                    portfolio_positions_map[pid] = open_positions
                    market_ids = {p['market_id'] for p in open_positions}
                    all_market_ids.update(market_ids)
                    logger.debug(f"Portfolio {pid}: {len(open_positions)} open positions in {len(market_ids)} markets")

            if not all_market_ids:
                logger.debug("No open positions across all portfolios, skipping price update")
                return

            logger.info(f"Fetching prices for {len(all_market_ids)} unique markets...")

            # Fetch current prices from Polymarket API (single batch call for all markets)
            current_prices = self._fetch_market_prices(list(all_market_ids))

            if not current_prices:
                logger.warning("No prices fetched, skipping P&L update")
                return

            # Update P&L for each portfolio independently
            for pid, open_positions in portfolio_positions_map.items():
                try:
                    self._update_portfolio_pnl_in_db(pid, open_positions, current_prices)
                except Exception as portfolio_error:
                    logger.error(f"Error updating portfolio {pid}: {portfolio_error}")

            # Store market snapshots for time-series data (once for all markets)
            for market_id, price_data in current_prices.items():
                insert_market_snapshot(market_id, price_data)

            logger.info(f"✓ Updated P&L for {len(portfolio_positions_map)} portfolios and stored market snapshots")

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

    def _close_position_on_resolution(
        self,
        position: Dict,
        exit_price: float,
        won_position: bool,
        portfolio_id: int
    ):
        """
        Close position when market resolves and update portfolio cash

        Args:
            position: Position dict with entry_price, amount, trade_id
            exit_price: Final price (0.0 or 1.0)
            won_position: True if position won
            portfolio_id: Portfolio ID
        """
        try:
            from src.db.operations import (
                close_portfolio_position,
                update_portfolio,
                get_portfolio
            )

            entry_price = position['entry_price']
            amount = position['amount']

            # Calculate realized P&L based on outcome
            # For prediction markets: P&L = amount * (exit_price - entry_price)
            realized_pnl = amount * (exit_price - entry_price)
            realized_pnl = round(realized_pnl, 2)

            # Determine cash returned based on outcome
            if won_position:
                # Win: Get back original investment
                cash_returned = amount
            else:
                # Loss: Lost the investment
                cash_returned = 0

            # Close position in database
            close_portfolio_position(
                trade_id=position['trade_id'],
                exit_price=exit_price,
                realized_pnl=realized_pnl,
                portfolio_id=portfolio_id
            )

            # Update portfolio balance and investment tracking
            portfolio = get_portfolio(portfolio_id)

            new_balance = portfolio['current_balance'] + cash_returned
            new_invested = portfolio['total_invested'] - amount
            new_total_pnl = portfolio['total_profit_loss'] + realized_pnl

            # Update win/loss statistics
            total_trades = portfolio['total_trades_executed']
            if realized_pnl > 0:
                new_winning_trades = portfolio['total_winning_trades'] + 1
                new_losing_trades = portfolio['total_losing_trades']
            elif realized_pnl < 0:
                new_winning_trades = portfolio['total_winning_trades']
                new_losing_trades = portfolio['total_losing_trades'] + 1
            else:
                new_winning_trades = portfolio['total_winning_trades']
                new_losing_trades = portfolio['total_losing_trades']

            # Calculate new average trade P&L
            if total_trades > 0:
                new_avg_pnl = new_total_pnl / total_trades
            else:
                new_avg_pnl = 0

            update_portfolio(portfolio_id, {
                'current_balance': new_balance,
                'total_invested': new_invested,
                'total_profit_loss': new_total_pnl,
                'total_winning_trades': new_winning_trades,
                'total_losing_trades': new_losing_trades,
                'avg_trade_pnl': round(new_avg_pnl, 2),
                'last_updated': datetime.now()
            })

            logger.info(
                f"Portfolio {portfolio_id}: Closed position {position['trade_id']} - "
                f"Market: {position['market_id']}, "
                f"Realized P&L: ${realized_pnl:.2f}, Cash returned: ${cash_returned:.2f}, "
                f"New balance: ${new_balance:.2f}"
            )

        except Exception as e:
            logger.error(f"Error closing position {position.get('trade_id')}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _update_portfolio_pnl_in_db(self, portfolio_id: int, open_positions: List[Dict], current_prices: Dict[str, Dict]):
        """
        Update portfolio P&L in database based on current market prices

        Args:
            portfolio_id: Portfolio to update
            open_positions: List of open positions for this portfolio
            current_prices: Dictionary of current market prices
        """
        try:
            from src.db.operations import update_portfolio_position, update_portfolio

            total_pnl = 0.0
            updated_positions = 0

            for position in open_positions:
                market_id = position.get('market_id')
                if market_id not in current_prices:
                    logger.warning(f"Portfolio {portfolio_id}: No current price for market {market_id}")
                    continue

                # Get current price based on action
                action = position.get('action')
                entry_price = position.get('entry_price', 0)
                amount = position.get('amount', 0)

                price_data = current_prices[market_id]

                if action == 'buy_yes':
                    current_price = price_data['yes_price']
                    # Check if market is resolved
                    is_resolved = (current_price == 1.0 or current_price == 0.0)
                    won_position = (current_price == 1.0)
                elif action == 'buy_no':
                    current_price = price_data['no_price']
                    # Check if market is resolved
                    is_resolved = (current_price == 1.0 or current_price == 0.0)
                    won_position = (current_price == 1.0)
                else:
                    logger.warning(f"Portfolio {portfolio_id}: Unknown action: {action}")
                    continue

                # If market is resolved, close position and skip normal P&L update
                if is_resolved:
                    logger.info(f"Portfolio {portfolio_id}: Market {market_id} resolved - closing position")
                    self._close_position_on_resolution(
                        position,
                        current_price,
                        won_position,
                        portfolio_id
                    )
                    continue  # Skip to next position

                # Calculate P&L for open (unresolved) positions
                # P&L = (current_price - entry_price) * amount
                position_pnl = (current_price - entry_price) * amount
                position_pnl_rounded = round(position_pnl, 2)

                # Update position in database
                update_portfolio_position(
                    position['trade_id'],
                    {'current_pnl': position_pnl_rounded},
                    portfolio_id=portfolio_id
                )

                total_pnl += position_pnl
                updated_positions += 1

                logger.debug(f"  Portfolio {portfolio_id}, Position {market_id}: entry={entry_price:.4f}, current={current_price:.4f}, P&L=${position_pnl:.2f}")

            # Update portfolio state with new total P&L
            update_portfolio(portfolio_id, {
                'total_profit_loss': round(total_pnl, 2),
                'last_price_update': datetime.now()
            })

            logger.info(f"Portfolio {portfolio_id}: Updated P&L for {updated_positions} open positions (Total P&L: ${total_pnl:.2f})")

        except Exception as e:
            logger.error(f"Error updating portfolio {portfolio_id} P&L in database: {e}")
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
