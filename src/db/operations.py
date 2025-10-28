"""
Database operations layer for Prescient OS
Phase 1: Portfolio & Trades
Phase 4: Events & Markets
"""

import os
import json
from typing import Dict, List, Optional
from datetime import datetime, date
from sqlalchemy import text
import logging

from src.db.connection import get_db

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _json_default_serializer(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

# ============================================================================
# PORTFOLIO OPERATIONS
# ============================================================================

def get_portfolio_state() -> Dict:
    """Get current portfolio state from database"""
    with get_db() as db:
        result = db.execute(text("""
            SELECT balance, total_invested, total_profit_loss, trade_count,
                   created_at, last_updated
            FROM portfolio_state
            WHERE id = 1
        """)).fetchone()

        if not result:
            # Initialize default portfolio on first run
            default_portfolio = {
                'id': 1,
                'balance': 10000.0,
                'total_invested': 0.0,
                'total_profit_loss': 0.0,
                'trade_count': 0,
                'created_at': datetime.now(),
                'last_updated': datetime.now()
            }
            db.execute(text("""
                INSERT INTO portfolio_state
                (id, balance, total_invested, total_profit_loss, trade_count, created_at, last_updated)
                VALUES (:id, :balance, :total_invested, :total_profit_loss, :trade_count, :created_at, :last_updated)
            """), default_portfolio)
            db.commit()
            return default_portfolio

        return {
            'balance': float(result[0]),
            'total_invested': float(result[1]),
            'total_profit_loss': float(result[2]),
            'trade_count': int(result[3]),
            'created_at': result[4],
            'last_updated': result[5]
        }


def upsert_portfolio_state(portfolio: Dict):
    """Update or insert portfolio state"""
    with get_db() as db:
        db.execute(text("""
            INSERT INTO portfolio_state
            (id, balance, total_invested, total_profit_loss, trade_count, created_at, last_updated)
            VALUES (1, :balance, :total_invested, :total_profit_loss, :trade_count,
                    :created_at, NOW())
            ON CONFLICT (id) DO UPDATE SET
                balance = EXCLUDED.balance,
                total_invested = EXCLUDED.total_invested,
                total_profit_loss = EXCLUDED.total_profit_loss,
                trade_count = EXCLUDED.trade_count,
                last_updated = NOW()
        """), {
            'balance': portfolio['balance'],
            'total_invested': portfolio['total_invested'],
            'total_profit_loss': portfolio['total_profit_loss'],
            'trade_count': portfolio['trade_count'],
            'created_at': portfolio.get('created_at', datetime.now())
        })
        db.commit()


def get_portfolio_positions(status: str = 'open') -> List[Dict]:
    """Get portfolio positions by status"""
    with get_db() as db:
        results = db.execute(text("""
            SELECT trade_id, market_id, market_question, action, amount,
                   entry_price, entry_timestamp, status, current_pnl,
                   realized_pnl, exit_price, exit_timestamp
            FROM portfolio_positions
            WHERE status = :status
            ORDER BY entry_timestamp DESC
        """), {'status': status}).fetchall()

        positions = []
        for row in results:
            positions.append({
                'trade_id': row[0],
                'market_id': row[1],
                'market_question': row[2],
                'action': row[3],
                'amount': float(row[4]),
                'entry_price': float(row[5]),
                'entry_timestamp': row[6].isoformat() if row[6] else None,
                'status': row[7],
                'current_pnl': float(row[8]) if row[8] else 0.0,
                'realized_pnl': float(row[9]) if row[9] else None,
                'exit_price': float(row[10]) if row[10] else None,
                'exit_timestamp': row[11].isoformat() if row[11] else None
            })

        return positions


def add_portfolio_position(position: Dict):
    """Add a new position to portfolio"""
    with get_db() as db:
        db.execute(text("""
            INSERT INTO portfolio_positions
            (trade_id, market_id, market_question, action, amount, entry_price,
             entry_timestamp, status, current_pnl)
            VALUES (:trade_id, :market_id, :market_question, :action, :amount,
                    :entry_price, :entry_timestamp, :status, :current_pnl)
        """), position)
        db.commit()


def update_portfolio_position(trade_id: str, updates: Dict):
    """Update a portfolio position"""
    with get_db() as db:
        set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
        query = f"""
            UPDATE portfolio_positions
            SET {set_clause}
            WHERE trade_id = :trade_id
        """
        updates['trade_id'] = trade_id
        db.execute(text(query), updates)
        db.commit()


def close_portfolio_position(trade_id: str, exit_price: float, realized_pnl: float):
    """Close a portfolio position"""
    with get_db() as db:
        db.execute(text("""
            UPDATE portfolio_positions
            SET status = 'closed',
                exit_price = :exit_price,
                exit_timestamp = NOW(),
                realized_pnl = :realized_pnl
            WHERE trade_id = :trade_id
        """), {
            'trade_id': trade_id,
            'exit_price': exit_price,
            'realized_pnl': realized_pnl
        })
        db.commit()


# ============================================================================
# TRADE OPERATIONS
# ============================================================================

def insert_trade(trade: Dict):
    """Insert a new trade into history"""
    with get_db() as db:
        db.execute(text("""
            INSERT INTO trades
            (trade_id, timestamp, market_id, market_question, action, amount,
             entry_price, confidence, reason, status, event_id, event_title,
             event_end_date, current_pnl, realized_pnl)
            VALUES (:trade_id, :timestamp, :market_id, :market_question, :action,
                    :amount, :entry_price, :confidence, :reason, :status,
                    :event_id, :event_title, :event_end_date, :current_pnl, :realized_pnl)
        """), trade)
        db.commit()


def get_trades(limit: int = None, status: str = None) -> List[Dict]:
    """Get trade history with optional filters"""
    with get_db() as db:
        query = """
            SELECT trade_id, timestamp, market_id, market_question, action, amount,
                   entry_price, confidence, reason, status, event_id, event_title,
                   event_end_date, current_pnl, realized_pnl
            FROM trades
        """

        params = {}
        if status:
            query += " WHERE status = :status"
            params['status'] = status

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT :limit"
            params['limit'] = limit

        results = db.execute(text(query), params).fetchall()

        trades = []
        for row in results:
            trades.append({
                'trade_id': row[0],
                'timestamp': row[1].isoformat() if row[1] else None,
                'market_id': row[2],
                'market_question': row[3],
                'action': row[4],
                'amount': float(row[5]),
                'entry_price': float(row[6]),
                'confidence': float(row[7]) if row[7] is not None else 0.0,
                'reason': row[8],
                'status': row[9],
                'event_id': row[10],
                'event_title': row[11],
                'event_end_date': row[12].isoformat() if row[12] else None,
                'current_pnl': float(row[13]) if row[13] else 0.0,
                'realized_pnl': float(row[14]) if row[14] else None
            })

        return trades


def get_trade_by_id(trade_id: str) -> Optional[Dict]:
    """Get a specific trade by ID"""
    with get_db() as db:
        result = db.execute(text("""
            SELECT trade_id, timestamp, market_id, market_question, action, amount,
                   entry_price, confidence, reason, status, event_id, event_title,
                   event_end_date, current_pnl, realized_pnl
            FROM trades
            WHERE trade_id = :trade_id
        """), {'trade_id': trade_id}).fetchone()

        if not result:
            return None

        return {
            'trade_id': result[0],
            'timestamp': result[1].isoformat() if result[1] else None,
            'market_id': result[2],
            'market_question': result[3],
            'action': result[4],
            'amount': float(result[5]),
            'entry_price': float(result[6]),
            'confidence': float(result[7]) if result[7] is not None else 0.0,
            'reason': result[8],
            'status': result[9],
            'event_id': result[10],
            'event_title': result[11],
            'event_end_date': result[12].isoformat() if result[12] else None,
            'current_pnl': float(result[13]) if result[13] else 0.0,
            'realized_pnl': float(result[14]) if result[14] else None
        }


def update_trade_status(trade_id: str, status: str, pnl: float = None):
    """Update trade status and PnL"""
    with get_db() as db:
        if pnl is not None:
            db.execute(text("""
                UPDATE trades
                SET status = :status,
                    realized_pnl = :pnl
                WHERE trade_id = :trade_id
            """), {'trade_id': trade_id, 'status': status, 'pnl': pnl})
        else:
            db.execute(text("""
                UPDATE trades
                SET status = :status
                WHERE trade_id = :trade_id
            """), {'trade_id': trade_id, 'status': status})
        db.commit()


# ============================================================================
# SIGNAL OPERATIONS (Phase 3)
# ============================================================================

def insert_signal(signal: Dict) -> int:
    """Insert a single trading signal and return its generated id."""
    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO trading_signals
            (timestamp, market_id, market_question, action, target_price, amount,
             confidence, reason, yes_price, no_price, market_liquidity, market_volume,
             event_id, event_title, event_end_date, executed, executed_at, trade_id)
            VALUES (:timestamp, :market_id, :market_question, :action, :target_price, :amount,
                    :confidence, :reason, :yes_price, :no_price, :market_liquidity, :market_volume,
                    :event_id, :event_title, :event_end_date, :executed, :executed_at, :trade_id)
            RETURNING id
        """), signal)
        inserted_id = result.scalar_one()
        db.commit()
        return int(inserted_id)


def insert_signals(signals: List[Dict]) -> List[int]:
    """Bulk insert trading signals in a single transaction; returns list of ids."""
    if not signals:
        return []

    with get_db() as db:
        inserted_ids: List[int] = []
        for signal in signals:
            result = db.execute(text("""
                INSERT INTO trading_signals
                (timestamp, market_id, market_question, action, target_price, amount,
                 confidence, reason, yes_price, no_price, market_liquidity, market_volume,
                 event_id, event_title, event_end_date, executed, executed_at, trade_id)
                VALUES (:timestamp, :market_id, :market_question, :action, :target_price, :amount,
                        :confidence, :reason, :yes_price, :no_price, :market_liquidity, :market_volume,
                        :event_id, :event_title, :event_end_date, :executed, :executed_at, :trade_id)
                RETURNING id
            """), signal)
            inserted_ids.append(int(result.scalar_one()))
        db.commit()
        return inserted_ids


def get_current_signals(limit: Optional[int] = None, executed: Optional[bool] = None) -> List[Dict]:
    """Query current signals ordered by timestamp DESC with optional executed filter and limit."""
    with get_db() as db:
        base_query = """
            SELECT id, timestamp, market_id, market_question, action, target_price, amount,
                   confidence, reason, yes_price, no_price, market_liquidity, market_volume,
                   event_id, event_title, event_end_date, executed, executed_at, trade_id
            FROM trading_signals
        """

        clauses = []
        params: Dict = {}
        if executed is not None:
            clauses.append("executed = :executed")
            params['executed'] = executed

        if clauses:
            base_query += " WHERE " + " AND ".join(clauses)

        base_query += " ORDER BY timestamp DESC"

        if limit:
            base_query += " LIMIT :limit"
            params['limit'] = limit

        rows = db.execute(text(base_query), params).fetchall()

        results: List[Dict] = []
        for row in rows:
            results.append({
                'id': int(row[0]),
                'timestamp': row[1],
                'market_id': row[2],
                'market_question': row[3],
                'action': row[4],
                'target_price': float(row[5]) if row[5] is not None else None,
                'amount': float(row[6]) if row[6] is not None else None,
                'confidence': float(row[7]) if row[7] is not None else None,
                'reason': row[8],
                'yes_price': float(row[9]) if row[9] is not None else None,
                'no_price': float(row[10]) if row[10] is not None else None,
                'market_liquidity': float(row[11]) if row[11] is not None else None,
                'market_volume': float(row[12]) if row[12] is not None else None,
                'event_id': row[13],
                'event_title': row[14],
                'event_end_date': row[15],
                'executed': bool(row[16]) if row[16] is not None else False,
                'executed_at': row[17],
                'trade_id': row[18]
            })
        return results


def mark_signal_executed(signal_id: int, trade_id: str, executed_at: Optional[datetime] = None):
    """Mark a signal executed and link to a trade id."""
    with get_db() as db:
        db.execute(text("""
            UPDATE trading_signals
            SET executed = TRUE,
                executed_at = COALESCE(:executed_at, NOW()),
                trade_id = :trade_id
            WHERE id = :signal_id
        """), {
            'signal_id': signal_id,
            'trade_id': trade_id,
            'executed_at': executed_at
        })
        db.commit()


# ============================================================================
# EVENT OPERATIONS (Phase 4)
# ============================================================================

def upsert_events(events: List[Dict]):
    """Insert or update events in database"""
    with get_db() as db:
        for event in events:
            # Create a copy to avoid modifying original
            event_copy = event.copy()

            # Convert datetime objects to ISO format strings for JSON serialization
            for key, value in event_copy.items():
                if isinstance(value, (datetime, date)):
                    event_copy[key] = value.isoformat()

            event_data_json = json.dumps(event_copy, default=_json_default_serializer)

            db.execute(text("""
                INSERT INTO events
                (event_id, title, slug, liquidity, volume, volume24hr,
                 start_date, end_date, days_until_end, event_data, is_filtered, updated_at)
                VALUES (:event_id, :title, :slug, :liquidity, :volume, :volume24hr,
                        :start_date, :end_date, :days_until_end, CAST(:event_data AS jsonb), :is_filtered, NOW())
                ON CONFLICT (event_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    slug = EXCLUDED.slug,
                    liquidity = EXCLUDED.liquidity,
                    volume = EXCLUDED.volume,
                    volume24hr = EXCLUDED.volume24hr,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    days_until_end = EXCLUDED.days_until_end,
                    event_data = EXCLUDED.event_data,
                    is_filtered = EXCLUDED.is_filtered,
                    updated_at = NOW()
            """), {
                'event_id': event.get('id'),
                'title': event.get('title'),
                'slug': event.get('slug'),
                'liquidity': event.get('liquidity', 0),
                'volume': event.get('volume', 0),
                'volume24hr': event.get('volume24hr', 0),
                'start_date': event.get('startDate'),
                'end_date': event.get('endDate'),
                'days_until_end': event.get('days_until_end'),
                'event_data': event_data_json,
                'is_filtered': event.get('is_filtered', False)
            })
        db.commit()


def get_events(filters: Dict = None) -> List[Dict]:
    """Get events with optional filters"""
    with get_db() as db:
        query = """
            SELECT event_id, title, slug, liquidity, volume, volume24hr,
                   start_date, end_date, days_until_end, event_data, is_filtered
            FROM events
        """

        params = {}
        where_clauses = []

        if filters:
            if 'is_filtered' in filters:
                where_clauses.append("is_filtered = :is_filtered")
                params['is_filtered'] = filters['is_filtered']

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY volume DESC"

        results = db.execute(text(query), params).fetchall()

        events = []
        for row in results:
            # PostgreSQL returns jsonb as dict already, no need to parse
            event_data = row[9] if row[9] else {}
            if isinstance(event_data, str):
                event_data = json.loads(event_data)

            event_data.update({
                'id': row[0],
                'title': row[1],
                'slug': row[2],
                'liquidity': float(row[3]) if row[3] else 0.0,
                'volume': float(row[4]) if row[4] else 0.0,
                'volume24hr': float(row[5]) if row[5] else 0.0,
                'startDate': row[6],
                'endDate': row[7],
                'days_until_end': row[8],
                'is_filtered': row[10]
            })
            events.append(event_data)

        return events


def clear_filtered_events():
    """Clear all filtered events (useful before re-filtering)"""
    with get_db() as db:
        db.execute(text("UPDATE events SET is_filtered = FALSE WHERE is_filtered = TRUE"))
        db.commit()


# ============================================================================
# MARKET OPERATIONS (Phase 4)
# ============================================================================

def upsert_markets(markets: List[Dict]):
    """Insert or update markets in database"""
    with get_db() as db:
        for market in markets:
            market_data_json = json.dumps(market, default=_json_default_serializer)
            db.execute(text("""
                INSERT INTO markets
                (market_id, question, event_id, event_title, event_end_date,
                 liquidity, volume, volume24hr, yes_price, no_price, market_conviction,
                 market_data, is_filtered, updated_at)
                VALUES (:market_id, :question, :event_id, :event_title, :event_end_date,
                        :liquidity, :volume, :volume24hr, :yes_price, :no_price,
                        :market_conviction, CAST(:market_data AS jsonb), :is_filtered, NOW())
                ON CONFLICT (market_id) DO UPDATE SET
                    question = EXCLUDED.question,
                    liquidity = EXCLUDED.liquidity,
                    volume = EXCLUDED.volume,
                    volume24hr = EXCLUDED.volume24hr,
                    yes_price = EXCLUDED.yes_price,
                    no_price = EXCLUDED.no_price,
                    market_conviction = EXCLUDED.market_conviction,
                    market_data = EXCLUDED.market_data,
                    is_filtered = EXCLUDED.is_filtered,
                    updated_at = NOW()
            """), {
                'market_id': market.get('id'),
                'question': market.get('question'),
                'event_id': market.get('event_id'),
                'event_title': market.get('event_title'),
                'event_end_date': market.get('event_end_date'),
                'liquidity': market.get('liquidity', 0),
                'volume': market.get('volume', 0),
                'volume24hr': market.get('volume24hr', 0),
                'yes_price': market.get('yes_price'),
                'no_price': market.get('no_price'),
                'market_conviction': market.get('market_conviction'),
                'market_data': market_data_json,
                'is_filtered': market.get('is_filtered', True)
            })
        db.commit()


def get_markets(filters: Dict = None) -> List[Dict]:
    """Get markets with optional filters"""
    with get_db() as db:
        query = """
            SELECT market_id, question, event_id, event_title, event_end_date,
                   liquidity, volume, volume24hr, yes_price, no_price,
                   market_conviction, market_data, is_filtered
            FROM markets
        """

        params = {}
        where_clauses = []

        if filters:
            if 'is_filtered' in filters:
                where_clauses.append("is_filtered = :is_filtered")
                params['is_filtered'] = filters['is_filtered']

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY volume DESC"

        results = db.execute(text(query), params).fetchall()

        markets = []
        for row in results:
            # PostgreSQL returns jsonb as dict already, no need to parse
            market_data = row[11] if row[11] else {}
            if isinstance(market_data, str):
                market_data = json.loads(market_data)

            market_data.update({
                'id': row[0],
                'question': row[1],
                'event_id': row[2],
                'event_title': row[3],
                'event_end_date': row[4],
                'liquidity': float(row[5]) if row[5] else 0.0,
                'volume': float(row[6]) if row[6] else 0.0,
                'volume24hr': float(row[7]) if row[7] else 0.0,
                'yes_price': float(row[8]) if row[8] else None,
                'no_price': float(row[9]) if row[9] else None,
                'market_conviction': float(row[10]) if row[10] else None,
                'is_filtered': row[12]
            })
            markets.append(market_data)

        return markets


def insert_market_snapshot(market_id: str, prices: Dict):
    """Insert a market price snapshot for time-series tracking"""
    with get_db() as db:
        db.execute(text("""
            INSERT INTO market_snapshots
            (market_id, yes_price, no_price, liquidity, volume, volume24hr, market_conviction)
            VALUES (:market_id, :yes_price, :no_price, :liquidity, :volume, :volume24hr, :market_conviction)
        """), {
            'market_id': market_id,
            'yes_price': prices.get('yes_price'),
            'no_price': prices.get('no_price'),
            'liquidity': prices.get('liquidity'),
            'volume': prices.get('volume'),
            'volume24hr': prices.get('volume24hr'),
            'market_conviction': prices.get('market_conviction')
        })
        db.commit()


def clear_filtered_markets():
    """Clear all filtered markets (useful before re-filtering)"""
    with get_db() as db:
        db.execute(text("UPDATE markets SET is_filtered = FALSE WHERE is_filtered = TRUE"))
        db.commit()
