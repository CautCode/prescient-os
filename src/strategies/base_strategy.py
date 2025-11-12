"""
Base Strategy Interface

Provides common utilities and enforces consistent API for all trading strategy controllers.
All strategy controllers should inherit from BaseStrategyController or follow its interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import requests
import logging

logger = logging.getLogger(__name__)


class BaseStrategyController(ABC):
    """
    Base class for all trading strategy controllers
    Defines the interface and common utilities
    """

    def __init__(self):
        self.events_api_base = "http://localhost:8000"
        self.markets_api_base = "http://localhost:8001"

    @abstractmethod
    def get_strategy_info(self) -> Dict:
        """
        Return strategy metadata

        Returns:
            Dictionary with strategy name, description, type, and default_config
        """
        pass

    @abstractmethod
    def generate_signals(self, markets_data: List[Dict], config: Dict) -> List[Dict]:
        """
        Generate signals using strategy logic

        Args:
            markets_data: List of filtered market dictionaries
            config: Strategy configuration parameters

        Returns:
            List of signal dictionaries
        """
        pass

    def export_events(self) -> Dict:
        """
        Export all active events from events controller
        Common utility used by all strategies

        Returns:
            API response from events controller
        """
        try:
            response = requests.get(
                f"{self.events_api_base}/events/export-all-active-events-db",
                timeout=300
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error exporting events: {e}")
            raise

    def filter_events(self, config: Dict) -> Dict:
        """
        Filter events using strategy config
        Common utility used by all strategies

        Args:
            config: Strategy configuration containing event filtering parameters

        Returns:
            API response from events controller
        """
        try:
            # Extract event filters from config
            params = self._extract_event_filters(config)

            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}

            logger.debug(f"Filtering events with params: {params}")

            response = requests.get(
                f"{self.events_api_base}/events/filter-trading-candidates-db",
                params=params,
                timeout=300
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error filtering events: {e}")
            raise

    def filter_markets(self, config: Dict) -> Dict:
        """
        Filter markets using strategy config
        Common utility used by all strategies

        Args:
            config: Strategy configuration containing market filtering parameters

        Returns:
            API response from markets controller
        """
        try:
            # Extract market filters from config
            params = self._extract_market_filters(config)

            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}

            logger.debug(f"Filtering markets with params: {params}")

            response = requests.get(
                f"{self.markets_api_base}/markets/export-filtered-markets-db",
                params=params,
                timeout=300
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error filtering markets: {e}")
            raise

    def _extract_event_filters(self, config: Dict) -> Dict:
        """
        Extract event filtering parameters from config

        Args:
            config: Strategy configuration dictionary

        Returns:
            Dictionary of event filtering parameters
        """
        return {
            "min_liquidity": config.get("event_min_liquidity"),
            "min_volume": config.get("event_min_volume"),
            "min_volume_24hr": config.get("event_min_volume_24hr"),
            "max_days_until_end": config.get("event_max_days_until_end"),
            "min_days_until_end": config.get("event_min_days_until_end")
        }

    def _extract_market_filters(self, config: Dict) -> Dict:
        """
        Extract market filtering parameters from config

        Args:
            config: Strategy configuration dictionary

        Returns:
            Dictionary of market filtering parameters
        """
        return {
            "min_liquidity": config.get("market_min_liquidity"),
            "min_volume": config.get("market_min_volume"),
            "min_volume_24hr": config.get("market_min_volume_24hr"),
            "min_market_conviction": config.get("market_min_conviction"),
            "max_market_conviction": config.get("market_max_conviction")
        }

    def merge_with_defaults(self, portfolio_config: Dict, default_config: Dict) -> Dict:
        """
        Merge portfolio strategy_config with strategy defaults
        Portfolio config takes precedence over defaults

        Args:
            portfolio_config: Configuration from portfolio.strategy_config
            default_config: Default configuration from strategy

        Returns:
            Merged configuration dictionary
        """
        merged = default_config.copy()
        merged.update(portfolio_config)
        return merged

    def prepare_signals_for_db(self, signals: List[Dict]) -> List[Dict]:
        """
        Prepare signals for database insertion
        Converts timestamps and ensures all required fields are present

        Args:
            signals: List of raw signal dictionaries

        Returns:
            List of prepared signal dictionaries
        """
        from datetime import datetime

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
