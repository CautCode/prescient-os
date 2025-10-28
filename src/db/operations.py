"""
Database operations layer for Prescient OS - Phase 1: Portfolio & Trades
Only includes operations needed for paper_trading_controller.py
"""

import os
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import text
import logging

from src.db.connection import get_db

logger = logging.getLogger(__name__)

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
