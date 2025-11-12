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

def _get_default_portfolio_id() -> int:
    """
    Get the default portfolio ID (first active portfolio)
    Used for backward compatibility when portfolio_id not specified
    """
    with get_db() as db:
        result = db.execute(text("""
            SELECT portfolio_id FROM portfolios
            WHERE status = 'active'
            ORDER BY portfolio_id ASC
            LIMIT 1
        """)).fetchone()

        if not result:
            raise ValueError("No active portfolios found")

        return int(result[0])


def create_portfolio(portfolio_data: Dict) -> int:
    """
    Create a new portfolio

    Args:
        portfolio_data: Dictionary with portfolio configuration

    Returns:
        Created portfolio_id

    Example:
        portfolio_id = create_portfolio({
            'name': 'Momentum Strategy',
            'description': 'High-confidence momentum trades',
            'strategy_type': 'momentum',
            'initial_balance': 50000,
            'current_balance': 50000,
            'strategy_config': {
                'min_confidence': 0.80,
                'market_types': ['politics']
            }
        })
    """
    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO portfolios
            (name, description, strategy_type, initial_balance, current_balance,
             strategy_config, status)
            VALUES (:name, :description, :strategy_type, :initial_balance, :current_balance,
                    CAST(:strategy_config AS jsonb), 'active')
            RETURNING portfolio_id
        """), {
            'name': portfolio_data['name'],
            'description': portfolio_data.get('description', ''),
            'strategy_type': portfolio_data['strategy_type'],
            'initial_balance': portfolio_data['initial_balance'],
            'current_balance': portfolio_data.get('current_balance', portfolio_data['initial_balance']),
            'strategy_config': json.dumps(portfolio_data.get('strategy_config', {}))
        })
        portfolio_id = result.scalar_one()
        db.commit()
        logger.info(f"Created portfolio {portfolio_id}: {portfolio_data['name']}")
        return int(portfolio_id)


def get_portfolio_state(portfolio_id: int = None) -> Dict:
    """
    Get portfolio state for specific portfolio or default if not specified

    Args:
        portfolio_id: Portfolio ID (defaults to first active portfolio)

    Returns:
        Portfolio state dictionary
    """
    if portfolio_id is None:
        # Get first active portfolio as default
        portfolio_id = _get_default_portfolio_id()

    with get_db() as db:
        result = db.execute(text("""
            SELECT portfolio_id, name, description, strategy_type,
                   initial_balance, current_balance, total_invested,
                   total_profit_loss, trade_count, status, created_at,
                   last_updated, strategy_config, last_trade_at, last_price_update
            FROM portfolios
            WHERE portfolio_id = :portfolio_id
        """), {'portfolio_id': portfolio_id}).fetchone()

        if not result:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        return {
            'portfolio_id': result[0],
            'name': result[1],
            'description': result[2],
            'strategy_type': result[3],
            'initial_balance': float(result[4]),
            'current_balance': float(result[5]),
            'total_invested': float(result[6]),
            'total_profit_loss': float(result[7]),
            'trade_count': int(result[8]),
            'status': result[9],
            'created_at': result[10],
            'last_updated': result[11],
            'strategy_config': result[12] or {},
            'last_trade_at': result[13],
            'last_price_update': result[14]
        }


def get_all_portfolios(status: str = None) -> List[Dict]:
    """
    Get all portfolios, optionally filtered by status

    Args:
        status: Filter by status ('active', 'paused', 'archived'), or None for all

    Returns:
        List of portfolio dictionaries
    """
    with get_db() as db:
        query = """
            SELECT portfolio_id, name, description, strategy_type,
                   initial_balance, current_balance, total_invested,
                   total_profit_loss, trade_count, status, created_at,
                   last_updated, strategy_config, last_trade_at, last_price_update
            FROM portfolios
        """

        params = {}
        if status:
            query += " WHERE status = :status"
            params['status'] = status

        query += " ORDER BY portfolio_id ASC"

        results = db.execute(text(query), params).fetchall()

        portfolios = []
        for row in results:
            portfolios.append({
                'portfolio_id': row[0],
                'name': row[1],
                'description': row[2],
                'strategy_type': row[3],
                'initial_balance': float(row[4]),
                'current_balance': float(row[5]),
                'total_invested': float(row[6]),
                'total_profit_loss': float(row[7]),
                'trade_count': int(row[8]),
                'status': row[9],
                'created_at': row[10],
                'last_updated': row[11],
                'strategy_config': row[12] or {},
                'last_trade_at': row[13],
                'last_price_update': row[14]
            })

        return portfolios


def update_portfolio(portfolio_id: int, updates: Dict):
    """
    Update portfolio fields

    Args:
        portfolio_id: Portfolio to update
        updates: Dictionary of fields to update

    Example:
        update_portfolio(1, {
            'current_balance': 9500.00,
            'total_invested': 500.00,
            'trade_count': 1,
            'status': 'active'
        })
    """
    with get_db() as db:
        # Build SET clause dynamically from updates dict
        set_clauses = [f"{key} = :{key}" for key in updates.keys()]
        set_clauses.append("last_updated = NOW()")
        set_clause = ", ".join(set_clauses)

        query = f"""
            UPDATE portfolios
            SET {set_clause}
            WHERE portfolio_id = :portfolio_id
        """

        updates['portfolio_id'] = portfolio_id

        # Handle JSONB fields
        if 'strategy_config' in updates and isinstance(updates['strategy_config'], dict):
            updates['strategy_config'] = json.dumps(updates['strategy_config'])

        db.execute(text(query), updates)
        db.commit()
        logger.debug(f"Updated portfolio {portfolio_id}: {list(updates.keys())}")


def pause_portfolio(portfolio_id: int, reason: str = None):
    """Pause a portfolio (stop trading but keep data)"""
    update_portfolio(portfolio_id, {'status': 'paused'})
    logger.info(f"Paused portfolio {portfolio_id}: {reason}")


def archive_portfolio(portfolio_id: int, reason: str = None):
    """Archive a portfolio (historical data only, no trading)"""
    update_portfolio(portfolio_id, {'status': 'archived'})
    logger.info(f"Archived portfolio {portfolio_id}: {reason}")


def delete_portfolio(portfolio_id: int):
    """
    Delete a portfolio and all associated data (CASCADE)
    WARNING: This is destructive and permanent
    """
    with get_db() as db:
        db.execute(text("""
            DELETE FROM portfolios WHERE portfolio_id = :portfolio_id
        """), {'portfolio_id': portfolio_id})
        db.commit()
        logger.warning(f"DELETED portfolio {portfolio_id} and all associated data")


# ============================================================================
# LEGACY PORTFOLIO OPERATIONS (for backward compatibility during migration)
# ============================================================================

def upsert_portfolio_state(portfolio: Dict):
    """
    DEPRECATED: Legacy function for backward compatibility
    Use update_portfolio() instead
    """
    logger.warning("upsert_portfolio_state is deprecated, use update_portfolio instead")
    # Try to update the default portfolio
    try:
        portfolio_id = _get_default_portfolio_id()
        update_portfolio(portfolio_id, {
            'current_balance': portfolio.get('balance', portfolio.get('current_balance')),
            'total_invested': portfolio['total_invested'],
            'total_profit_loss': portfolio['total_profit_loss'],
            'trade_count': portfolio['trade_count']
        })
    except ValueError:
        logger.error("No default portfolio found for legacy upsert_portfolio_state")


def get_portfolio_positions(portfolio_id: int = None, status: str = 'open') -> List[Dict]:
    """
    Get portfolio positions by portfolio and status

    Args:
        portfolio_id: Portfolio ID (defaults to first active portfolio)
        status: Position status filter ('open', 'closed', etc.)
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    with get_db() as db:
        results = db.execute(text("""
            SELECT portfolio_id, trade_id, market_id, market_question, action, amount,
                   entry_price, entry_timestamp, status, current_pnl,
                   realized_pnl, exit_price, exit_timestamp
            FROM portfolio_positions
            WHERE portfolio_id = :portfolio_id AND status = :status
            ORDER BY entry_timestamp DESC
        """), {'portfolio_id': portfolio_id, 'status': status}).fetchall()

        positions = []
        for row in results:
            positions.append({
                'portfolio_id': row[0],
                'trade_id': row[1],
                'market_id': row[2],
                'market_question': row[3],
                'action': row[4],
                'amount': float(row[5]),
                'entry_price': float(row[6]),
                'entry_timestamp': row[7].isoformat() if row[7] else None,
                'status': row[8],
                'current_pnl': float(row[9]) if row[9] else 0.0,
                'realized_pnl': float(row[10]) if row[10] else None,
                'exit_price': float(row[11]) if row[11] else None,
                'exit_timestamp': row[12].isoformat() if row[12] else None
            })

        return positions


def add_portfolio_position(position: Dict, portfolio_id: int = None):
    """
    Add a new position to portfolio

    Args:
        position: Position data dictionary
        portfolio_id: Portfolio ID (defaults to first active portfolio)
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    position['portfolio_id'] = portfolio_id

    with get_db() as db:
        db.execute(text("""
            INSERT INTO portfolio_positions
            (portfolio_id, trade_id, market_id, market_question, action, amount, entry_price,
             entry_timestamp, status, current_pnl)
            VALUES (:portfolio_id, :trade_id, :market_id, :market_question, :action, :amount,
                    :entry_price, :entry_timestamp, :status, :current_pnl)
        """), position)
        db.commit()
        logger.debug(f"Added position to portfolio {portfolio_id}: {position['trade_id']}")


def update_portfolio_position(trade_id: str, updates: Dict, portfolio_id: int = None):
    """
    Update a portfolio position

    Args:
        trade_id: Trade ID to update
        updates: Dictionary of fields to update
        portfolio_id: Portfolio ID (optional, for additional safety)
    """
    with get_db() as db:
        set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])

        # Build WHERE clause
        where_clause = "trade_id = :trade_id"
        if portfolio_id is not None:
            where_clause += " AND portfolio_id = :portfolio_id"
            updates['portfolio_id'] = portfolio_id

        query = f"""
            UPDATE portfolio_positions
            SET {set_clause}
            WHERE {where_clause}
        """
        updates['trade_id'] = trade_id
        db.execute(text(query), updates)
        db.commit()
        logger.debug(f"Updated position {trade_id} in portfolio {portfolio_id}")


def close_portfolio_position(trade_id: str, exit_price: float, realized_pnl: float, portfolio_id: int = None):
    """
    Close a portfolio position

    Args:
        trade_id: Trade ID to close
        exit_price: Exit price
        realized_pnl: Realized profit/loss
        portfolio_id: Portfolio ID (optional, for additional safety)
    """
    with get_db() as db:
        # Build WHERE clause
        where_clause = "trade_id = :trade_id"
        params = {
            'trade_id': trade_id,
            'exit_price': exit_price,
            'realized_pnl': realized_pnl
        }

        if portfolio_id is not None:
            where_clause += " AND portfolio_id = :portfolio_id"
            params['portfolio_id'] = portfolio_id

        # Update portfolio_positions table
        query = f"""
            UPDATE portfolio_positions
            SET status = 'closed',
                exit_price = :exit_price,
                exit_timestamp = NOW(),
                realized_pnl = :realized_pnl
            WHERE {where_clause}
        """
        db.execute(text(query), params)

        # Also update trades table to keep in sync
        trades_query = f"""
            UPDATE trades
            SET status = 'closed',
                realized_pnl = :realized_pnl
            WHERE {where_clause}
        """
        db.execute(text(trades_query), params)

        db.commit()
        logger.info(f"Closed position {trade_id} in portfolio {portfolio_id}: PnL ${realized_pnl}")


# ============================================================================
# TRADE OPERATIONS
# ============================================================================

def insert_trade(trade: Dict, portfolio_id: int = None):
    """
    Insert a new trade into history

    Args:
        trade: Trade data dictionary
        portfolio_id: Portfolio ID (defaults to first active portfolio)
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    trade['portfolio_id'] = portfolio_id

    with get_db() as db:
        db.execute(text("""
            INSERT INTO trades
            (portfolio_id, trade_id, timestamp, market_id, market_question, action, amount,
             entry_price, confidence, reason, status, event_id, event_title,
             event_end_date, current_pnl, realized_pnl)
            VALUES (:portfolio_id, :trade_id, :timestamp, :market_id, :market_question, :action,
                    :amount, :entry_price, :confidence, :reason, :status,
                    :event_id, :event_title, :event_end_date, :current_pnl, :realized_pnl)
        """), trade)
        db.commit()
        logger.info(f"Inserted trade {trade['trade_id']} for portfolio {portfolio_id}")


def get_trades(portfolio_id: int = None, limit: int = None, status: str = None) -> List[Dict]:
    """
    Get trade history with optional filters

    Args:
        portfolio_id: Portfolio ID (defaults to first active portfolio)
        limit: Maximum number of trades to return
        status: Filter by trade status
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    with get_db() as db:
        query = """
            SELECT portfolio_id, trade_id, timestamp, market_id, market_question, action, amount,
                   entry_price, confidence, reason, status, event_id, event_title,
                   event_end_date, current_pnl, realized_pnl
            FROM trades
            WHERE portfolio_id = :portfolio_id
        """

        params = {'portfolio_id': portfolio_id}

        if status:
            query += " AND status = :status"
            params['status'] = status

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT :limit"
            params['limit'] = limit

        results = db.execute(text(query), params).fetchall()

        trades = []
        for row in results:
            trades.append({
                'portfolio_id': row[0],
                'trade_id': row[1],
                'timestamp': row[2].isoformat() if row[2] else None,
                'market_id': row[3],
                'market_question': row[4],
                'action': row[5],
                'amount': float(row[6]),
                'entry_price': float(row[7]),
                'confidence': float(row[8]) if row[8] is not None else 0.0,
                'reason': row[9],
                'status': row[10],
                'event_id': row[11],
                'event_title': row[12],
                'event_end_date': row[13].isoformat() if row[13] else None,
                'current_pnl': float(row[14]) if row[14] else 0.0,
                'realized_pnl': float(row[15]) if row[15] else None
            })

        return trades


def get_trade_by_id(trade_id: str, portfolio_id: int = None) -> Optional[Dict]:
    """
    Get a specific trade by ID

    Args:
        trade_id: Trade ID
        portfolio_id: Portfolio ID (optional, for additional filtering)
    """
    with get_db() as db:
        query = """
            SELECT portfolio_id, trade_id, timestamp, market_id, market_question, action, amount,
                   entry_price, confidence, reason, status, event_id, event_title,
                   event_end_date, current_pnl, realized_pnl
            FROM trades
            WHERE trade_id = :trade_id
        """

        params = {'trade_id': trade_id}

        if portfolio_id is not None:
            query += " AND portfolio_id = :portfolio_id"
            params['portfolio_id'] = portfolio_id

        result = db.execute(text(query), params).fetchone()

        if not result:
            return None

        return {
            'portfolio_id': result[0],
            'trade_id': result[1],
            'timestamp': result[2].isoformat() if result[2] else None,
            'market_id': result[3],
            'market_question': result[4],
            'action': result[5],
            'amount': float(result[6]),
            'entry_price': float(result[7]),
            'confidence': float(result[8]) if result[8] is not None else 0.0,
            'reason': result[9],
            'status': result[10],
            'event_id': result[11],
            'event_title': result[12],
            'event_end_date': result[13].isoformat() if result[13] else None,
            'current_pnl': float(result[14]) if result[14] else 0.0,
            'realized_pnl': float(result[15]) if result[15] else None
        }


def update_trade_status(trade_id: str, status: str, pnl: float = None, portfolio_id: int = None):
    """
    Update trade status and PnL

    Args:
        trade_id: Trade ID to update
        status: New status
        pnl: Realized PnL (optional)
        portfolio_id: Portfolio ID (optional, for additional safety)
    """
    with get_db() as db:
        where_clause = "trade_id = :trade_id"
        params = {'trade_id': trade_id, 'status': status}

        if portfolio_id is not None:
            where_clause += " AND portfolio_id = :portfolio_id"
            params['portfolio_id'] = portfolio_id

        if pnl is not None:
            params['pnl'] = pnl
            query = f"""
                UPDATE trades
                SET status = :status,
                    realized_pnl = :pnl
                WHERE {where_clause}
            """
        else:
            query = f"""
                UPDATE trades
                SET status = :status
                WHERE {where_clause}
            """

        db.execute(text(query), params)
        db.commit()
        logger.debug(f"Updated trade {trade_id} status to {status}")


# ============================================================================
# SIGNAL OPERATIONS (Phase 3)
# ============================================================================

def insert_signal(signal: Dict, portfolio_id: int = None) -> int:
    """
    Insert a single trading signal and return its generated id

    Args:
        signal: Signal data dictionary
        portfolio_id: Portfolio ID (defaults to first active portfolio)
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    signal['portfolio_id'] = portfolio_id

    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO trading_signals
            (portfolio_id, strategy_type, timestamp, market_id, market_question, action, target_price, amount,
             confidence, reason, yes_price, no_price, market_liquidity, market_volume,
             event_id, event_title, event_end_date, executed, executed_at, trade_id)
            VALUES (:portfolio_id, :strategy_type, :timestamp, :market_id, :market_question, :action, :target_price, :amount,
                    :confidence, :reason, :yes_price, :no_price, :market_liquidity, :market_volume,
                    :event_id, :event_title, :event_end_date, :executed, :executed_at, :trade_id)
            RETURNING id
        """), signal)
        inserted_id = result.scalar_one()
        db.commit()
        logger.debug(f"Inserted signal for portfolio {portfolio_id}: {signal.get('market_id')}")
        return int(inserted_id)


def insert_signals(signals: List[Dict], portfolio_id: int = None) -> List[int]:
    """
    Bulk insert trading signals in a single transaction; returns list of ids

    Args:
        signals: List of signal data dictionaries
        portfolio_id: Portfolio ID (defaults to first active portfolio)
    """
    if not signals:
        return []

    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    with get_db() as db:
        inserted_ids: List[int] = []
        for signal in signals:
            signal['portfolio_id'] = portfolio_id

            result = db.execute(text("""
                INSERT INTO trading_signals
                (portfolio_id, strategy_type, timestamp, market_id, market_question, action, target_price, amount,
                 confidence, reason, yes_price, no_price, market_liquidity, market_volume,
                 event_id, event_title, event_end_date, executed, executed_at, trade_id)
                VALUES (:portfolio_id, :strategy_type, :timestamp, :market_id, :market_question, :action, :target_price, :amount,
                        :confidence, :reason, :yes_price, :no_price, :market_liquidity, :market_volume,
                        :event_id, :event_title, :event_end_date, :executed, :executed_at, :trade_id)
                RETURNING id
            """), signal)
            inserted_ids.append(int(result.scalar_one()))
        db.commit()
        logger.info(f"Inserted {len(inserted_ids)} signals for portfolio {portfolio_id}")
        return inserted_ids


def get_current_signals(portfolio_id: int = None, limit: Optional[int] = None, executed: Optional[bool] = None) -> List[Dict]:
    """
    Query current signals ordered by timestamp DESC with optional filters

    Args:
        portfolio_id: Portfolio ID (defaults to first active portfolio)
        limit: Maximum number of signals to return
        executed: Filter by executed status
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    with get_db() as db:
        base_query = """
            SELECT id, portfolio_id, strategy_type, timestamp, market_id, market_question, action, target_price, amount,
                   confidence, reason, yes_price, no_price, market_liquidity, market_volume,
                   event_id, event_title, event_end_date, executed, executed_at, trade_id
            FROM trading_signals
        """

        clauses = ["portfolio_id = :portfolio_id"]
        params: Dict = {'portfolio_id': portfolio_id}

        if executed is not None:
            clauses.append("executed = :executed")
            params['executed'] = executed

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
                'portfolio_id': row[1],
                'strategy_type': row[2],
                'timestamp': row[3],
                'market_id': row[4],
                'market_question': row[5],
                'action': row[6],
                'target_price': float(row[7]) if row[7] is not None else None,
                'amount': float(row[8]) if row[8] is not None else None,
                'confidence': float(row[9]) if row[9] is not None else None,
                'reason': row[10],
                'yes_price': float(row[11]) if row[11] is not None else None,
                'no_price': float(row[12]) if row[12] is not None else None,
                'market_liquidity': float(row[13]) if row[13] is not None else None,
                'market_volume': float(row[14]) if row[14] is not None else None,
                'event_id': row[15],
                'event_title': row[16],
                'event_end_date': row[17],
                'executed': bool(row[18]) if row[18] is not None else False,
                'executed_at': row[19],
                'trade_id': row[20]
            })
        return results


def mark_signal_executed(signal_id: int, trade_id: str, executed_at: Optional[datetime] = None, portfolio_id: int = None):
    """
    Mark a signal executed and link to a trade id

    Args:
        signal_id: Signal ID to mark as executed
        trade_id: Associated trade ID
        executed_at: Execution timestamp (defaults to NOW())
        portfolio_id: Portfolio ID (optional, for additional safety)
    """
    with get_db() as db:
        where_clause = "id = :signal_id"
        params = {
            'signal_id': signal_id,
            'trade_id': trade_id,
            'executed_at': executed_at
        }

        if portfolio_id is not None:
            where_clause += " AND portfolio_id = :portfolio_id"
            params['portfolio_id'] = portfolio_id

        query = f"""
            UPDATE trading_signals
            SET executed = TRUE,
                executed_at = COALESCE(:executed_at, NOW()),
                trade_id = :trade_id
            WHERE {where_clause}
        """

        db.execute(text(query), params)
        db.commit()
        logger.debug(f"Marked signal {signal_id} as executed with trade {trade_id}")


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
                (id, title, slug, liquidity, volume, volume24hr,
                 end_date, is_filtered, last_updated)
                VALUES (:id, :title, :slug, :liquidity, :volume, :volume24hr,
                        :end_date, :is_filtered, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    slug = EXCLUDED.slug,
                    liquidity = EXCLUDED.liquidity,
                    volume = EXCLUDED.volume,
                    volume24hr = EXCLUDED.volume24hr,
                    end_date = EXCLUDED.end_date,
                    is_filtered = EXCLUDED.is_filtered,
                    last_updated = NOW()
            """), {
                'id': event.get('id'),
                'title': event.get('title'),
                'slug': event.get('slug'),
                'liquidity': event.get('liquidity', 0),
                'volume': event.get('volume', 0),
                'volume24hr': event.get('volume24hr', 0),
                'end_date': event.get('endDate'),
                'is_filtered': event.get('is_filtered', False)
            })
        db.commit()


def get_events(filters: Dict = None) -> List[Dict]:
    """Get events with optional filters"""
    with get_db() as db:
        query = """
            SELECT id, title, slug, liquidity, volume, volume24hr, end_date, is_filtered
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
            event = {
                'id': row[0],
                'title': row[1],
                'slug': row[2],
                'liquidity': float(row[3]) if row[3] else 0.0,
                'volume': float(row[4]) if row[4] else 0.0,
                'volume24hr': float(row[5]) if row[5] else 0.0,
                'endDate': row[6],
                'is_filtered': row[7]
            }
            events.append(event)

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
            db.execute(text("""
                INSERT INTO markets
                (id, question, event_id, event_title, end_date,
                 liquidity, volume, volume24hr, yes_price, no_price, market_conviction,
                 is_filtered, last_updated)
                VALUES (:id, :question, :event_id, :event_title, :end_date,
                        :liquidity, :volume, :volume24hr, :yes_price, :no_price,
                        :market_conviction, :is_filtered, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    question = EXCLUDED.question,
                    event_id = EXCLUDED.event_id,
                    event_title = EXCLUDED.event_title,
                    end_date = EXCLUDED.end_date,
                    liquidity = EXCLUDED.liquidity,
                    volume = EXCLUDED.volume,
                    volume24hr = EXCLUDED.volume24hr,
                    yes_price = EXCLUDED.yes_price,
                    no_price = EXCLUDED.no_price,
                    market_conviction = EXCLUDED.market_conviction,
                    is_filtered = EXCLUDED.is_filtered,
                    last_updated = NOW()
            """), {
                'id': market.get('id'),
                'question': market.get('question'),
                'event_id': market.get('event_id'),
                'event_title': market.get('event_title'),
                'end_date': market.get('event_end_date') or market.get('endDate'),
                'liquidity': market.get('liquidity', 0),
                'volume': market.get('volume', 0),
                'volume24hr': market.get('volume24hr', 0),
                'yes_price': market.get('yes_price'),
                'no_price': market.get('no_price'),
                'market_conviction': market.get('market_conviction'),
                'is_filtered': market.get('is_filtered', True)
            })
        db.commit()


def get_markets(filters: Dict = None) -> List[Dict]:
    """Get markets with optional filters"""
    with get_db() as db:
        query = """
            SELECT id, question, event_id, event_title, end_date,
                   liquidity, volume, volume24hr, yes_price, no_price,
                   market_conviction, is_filtered
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
            market = {
                'id': row[0],
                'question': row[1],
                'event_id': row[2],
                'event_title': row[3],
                'event_end_date': row[4],
                'endDate': row[4],  # Also provide endDate for compatibility
                'liquidity': float(row[5]) if row[5] else 0.0,
                'volume': float(row[6]) if row[6] else 0.0,
                'volume24hr': float(row[7]) if row[7] else 0.0,
                'yes_price': float(row[8]) if row[8] else None,
                'no_price': float(row[9]) if row[9] else None,
                'market_conviction': float(row[10]) if row[10] else None,
                'is_filtered': row[11]
            }
            markets.append(market)

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


# ============================================================================
# HISTORY OPERATIONS (Phase 2)
# ============================================================================

def insert_portfolio_history_snapshot(snapshot: Dict, portfolio_id: int = None) -> int:
    """
    Insert a single portfolio history snapshot and return its id

    Args:
        snapshot: Snapshot data dictionary
        portfolio_id: Portfolio ID (defaults to first active portfolio)
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    snapshot['portfolio_id'] = portfolio_id

    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO portfolio_history
            (portfolio_id, snapshot_date, timestamp, balance, total_invested, total_profit_loss,
             total_value, open_positions, trade_count)
            VALUES (:portfolio_id, :snapshot_date, :timestamp, :balance, :total_invested, :total_profit_loss,
                    :total_value, :open_positions, :trade_count)
            RETURNING id
        """), snapshot)
        inserted_id = result.scalar_one()
        db.commit()
        logger.debug(f"Created portfolio history snapshot for portfolio {portfolio_id}")
        return int(inserted_id)


def get_portfolio_history(portfolio_id: int = None, limit: Optional[int] = None) -> List[Dict]:
    """
    Return recent portfolio history rows ordered by date/time descending

    Args:
        portfolio_id: Portfolio ID (defaults to first active portfolio)
        limit: Maximum number of snapshots to return
    """
    if portfolio_id is None:
        portfolio_id = _get_default_portfolio_id()

    with get_db() as db:
        query = """
            SELECT id, portfolio_id, snapshot_date, timestamp, balance, total_invested,
                   total_profit_loss, total_value, open_positions, trade_count
            FROM portfolio_history
            WHERE portfolio_id = :portfolio_id
            ORDER BY snapshot_date DESC, timestamp DESC
        """

        params: Dict = {'portfolio_id': portfolio_id}
        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        rows = db.execute(text(query), params).fetchall()
        results: List[Dict] = []
        for row in rows:
            results.append({
                'id': int(row[0]),
                'portfolio_id': row[1],
                'snapshot_date': row[2],
                'timestamp': row[3],
                'balance': float(row[4]) if row[4] is not None else None,
                'total_invested': float(row[5]) if row[5] is not None else None,
                'total_profit_loss': float(row[6]) if row[6] is not None else None,
                'total_value': float(row[7]) if row[7] is not None else None,
                'open_positions': int(row[8]) if row[8] is not None else 0,
                'trade_count': int(row[9]) if row[9] is not None else 0,
            })
        return results


def insert_signal_archive(archived_at: datetime, signals: List[Dict]) -> int:
    """Insert a signal archive row storing signals JSON and return its id."""
    archive_month = archived_at.strftime('%Y-%m')
    signals_count = len(signals) if signals else 0
    signals_json = json.dumps(signals, default=_json_default_serializer)

    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO signal_archives
            (archived_at, archive_month, signals_count, signals_data)
            VALUES (:archived_at, :archive_month, :signals_count, CAST(:signals_data AS jsonb))
            RETURNING id
        """), {
            'archived_at': archived_at,
            'archive_month': archive_month,
            'signals_count': signals_count,
            'signals_data': signals_json,
        })
        inserted_id = result.scalar_one()
        db.commit()
        return int(inserted_id)


def get_recent_signal_archives(limit: Optional[int] = None) -> List[Dict]:
    """Return recent signal archives ordered by archived_at DESC."""
    with get_db() as db:
        query = (
            """
            SELECT id, archived_at, archive_month, signals_count, signals_data
            FROM signal_archives
            ORDER BY archived_at DESC
            """
        )

        params: Dict = {}
        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        rows = db.execute(text(query), params).fetchall()
        results: List[Dict] = []
        for row in rows:
            signals_data = row[4]
            if isinstance(signals_data, str):
                try:
                    signals_data = json.loads(signals_data)
                except Exception:
                    signals_data = []

            results.append({
                'id': int(row[0]),
                'archived_at': row[1],
                'archive_month': row[2],
                'signals_count': int(row[3]) if row[3] is not None else 0,
                'signals_data': signals_data if signals_data is not None else [],
            })
        return results