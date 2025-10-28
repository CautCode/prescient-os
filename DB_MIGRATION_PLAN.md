# PostgreSQL Migration Plan - Phase 1: Trades & Portfolio

**Created:** 2025-10-28
**Status:** Planning Phase
**Approach:** Phase 1 only - Start fresh with PostgreSQL (no JSON migration needed)
**Scope:** Paper trading controller only - other controllers remain unchanged

---

## Table of Contents

1. [Overview](#overview)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [Phase 1 Scope](#phase-1-scope)
4. [Database Operations Layer](#database-operations-layer)
5. [Implementation Steps](#implementation-steps)
6. [Testing Strategy](#testing-strategy)
7. [Rollback Plan](#rollback-plan)
8. [Success Criteria](#success-criteria)

---

## Overview

### Current State
- Portfolio data in `data/trades/portfolio.json`
- Trade history in `data/trades/paper_trades.json`
- Paper trading controller manages all trade operations

### Phase 1 Target State
- **Portfolio and trades** stored in PostgreSQL
- **Paper trading controller** uses database operations
- **Events, markets, and signals** remain in JSON (migrate later)
- **Start fresh** - No need to migrate existing JSON data
- Existing JSON files archived for historical reference only

### Key Decisions
✅ **Phase 1 only** - Focus on `paper_trading_controller.py`
✅ **Start fresh in database** - No JSON-to-DB migration needed
✅ **Keep other controllers unchanged** - Events/markets/signals stay in JSON
✅ **Create minimal operations layer** - Only portfolio and trade operations
✅ **Archive existing JSON** - Keep as backup but start with fresh portfolio

---

## Pre-Migration Checklist

### Infrastructure Ready ✅
- [x] PostgreSQL 16 installed and running
- [x] Database `prescient_os` created
- [x] User `prescient_user` created with permissions
- [x] Schema applied (`src/db/schema.sql`)
- [x] Python packages installed (`psycopg2-binary`, `sqlalchemy`)
- [x] Connection manager created (`src/db/connection.py`)
- [x] Connection test passes

### Before Starting Phase 1
- [ ] Archive existing JSON files: `mkdir data_backup && cp -r data/* data_backup/`
- [ ] Verify database tables exist: `portfolio_state`, `portfolio_positions`, `trades`
- [ ] Document current portfolio value (if needed for reference)

---

## Phase 1 Scope

### What's Included in Phase 1
✅ **Paper Trading Controller** (`src/paper_trading_controller.py`)
  - Portfolio management (load/save)
  - Trade execution and history
  - Position tracking

✅ **Database Tables Used**
  - `portfolio_state` - Current portfolio state
  - `portfolio_positions` - Open positions
  - `trades` - Trade history

✅ **New Files**
  - `src/db/operations.py` - Portfolio and trade operations only

### What's NOT Included (Future Phases)
❌ Events controller - stays in JSON
❌ Markets controller - stays in JSON
❌ Trading strategy controller - stays in JSON (signals remain in JSON)
❌ Price updater - will be migrated later

### Why Phase 1 First?
1. **Most critical data** - Portfolio and trade history are the business core
2. **Simplest to migrate** - Single controller, clear data boundaries
3. **Low risk** - Other controllers continue working with JSON
4. **Easy rollback** - Can revert just this controller if needed
5. **Fresh start** - Clean database with proper schema from day one

---

## Database Operations Layer

### `src/db/operations.py` - Phase 1 Functions Only

Create this file with **only** portfolio and trade operations:

```python
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
                'confidence': float(row[7]),
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
            'confidence': float(result[7]),
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
```

---

## Implementation Steps

### Step 1: Create Database Operations File

Create `src/db/operations.py` with the full code provided above.

**Verification:**
```bash
python -c "from src.db.operations import get_portfolio_state; print(get_portfolio_state())"
```

Expected output: Fresh portfolio with $10,000 balance

### Step 2: Update Paper Trading Controller

Modify `src/paper_trading_controller.py`:

**Replace `load_portfolio()` function:**
```python
def load_portfolio() -> Dict:
    """Load portfolio from database"""
    from src.db.operations import get_portfolio_state, get_portfolio_positions

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
    return portfolio
```

**Replace `save_portfolio()` function:**
```python
def save_portfolio(portfolio: Dict):
    """Save portfolio to database"""
    from src.db.operations import upsert_portfolio_state

    upsert_portfolio_state(portfolio)
    logger.debug(f"Saved portfolio to database with balance: ${portfolio.get('balance', 0):.2f}")
```

**Replace `append_trade_to_history()` function:**
```python
def append_trade_to_history(trade: Dict):
    """Append a trade to history in database"""
    from src.db.operations import insert_trade, add_portfolio_position

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
```

**Remove these functions (no longer needed):**
- `initialize_portfolio()` - DB auto-initializes
- `ensure_data_directories()` - Not needed for database

### Step 3: Archive Existing JSON Files

```bash
# Create backup directory
mkdir data_backup_20251028

# Move portfolio and trade files
mv data/trades/portfolio.json data_backup_20251028/
mv data/trades/paper_trades.json data_backup_20251028/
```

Keep these as historical reference, but system will use database going forward.

### Step 4: Test the Migration

**Test 1: Portfolio initialization**
```bash
curl http://localhost:8000/paper-trading/portfolio
```
Expected: Fresh portfolio with $10,000 balance

**Test 2: Execute a test trade**
```bash
curl -X POST http://localhost:8000/paper-trading/execute
```
Expected: Trade saved to database, portfolio updated

**Test 3: View trade history**
```bash
curl http://localhost:8000/paper-trading/history
```
Expected: Trade appears in history from database

**Test 4: Verify in PostgreSQL**
```sql
-- Check portfolio
SELECT * FROM portfolio_state;

-- Check positions
SELECT * FROM portfolio_positions;

-- Check trades
SELECT * FROM trades;
```

---

## Testing Strategy

### Unit Tests

Create `tests/test_db_operations.py`:

```python
import pytest
from src.db.operations import (
    get_portfolio_state,
    upsert_portfolio_state,
    add_portfolio_position,
    get_portfolio_positions,
    insert_trade,
    get_trades
)

def test_portfolio_initialization():
    """Test that portfolio initializes with default values"""
    portfolio = get_portfolio_state()
    assert portfolio['balance'] == 10000.0
    assert portfolio['total_invested'] == 0.0
    assert portfolio['trade_count'] == 0

def test_portfolio_update():
    """Test portfolio state updates"""
    portfolio = get_portfolio_state()
    portfolio['balance'] = 9500.0
    portfolio['total_invested'] = 500.0

    upsert_portfolio_state(portfolio)

    updated = get_portfolio_state()
    assert updated['balance'] == 9500.0
    assert updated['total_invested'] == 500.0

def test_add_position():
    """Test adding a position"""
    position = {
        'trade_id': 'test_123',
        'market_id': 'market_456',
        'market_question': 'Test market?',
        'action': 'buy_yes',
        'amount': 100.0,
        'entry_price': 0.55,
        'entry_timestamp': '2025-10-28T12:00:00',
        'status': 'open',
        'current_pnl': 0.0
    }

    add_portfolio_position(position)

    positions = get_portfolio_positions(status='open')
    assert len(positions) >= 1
    assert positions[0]['trade_id'] == 'test_123'

def test_insert_trade():
    """Test inserting a trade"""
    trade = {
        'trade_id': 'trade_789',
        'timestamp': '2025-10-28T12:00:00',
        'market_id': 'market_456',
        'market_question': 'Test market?',
        'action': 'buy_yes',
        'amount': 100.0,
        'entry_price': 0.55,
        'confidence': 0.75,
        'reason': 'Test trade',
        'status': 'open',
        'event_id': 'event_123',
        'event_title': 'Test Event',
        'event_end_date': '2025-11-01T00:00:00',
        'current_pnl': 0.0,
        'realized_pnl': None
    }

    insert_trade(trade)

    trades = get_trades(limit=1)
    assert len(trades) == 1
    assert trades[0]['trade_id'] == 'trade_789'
```

Run tests:
```bash
pytest tests/test_db_operations.py -v
```

### Integration Tests

**Test full trading workflow:**
1. Initialize portfolio (GET /paper-trading/portfolio)
2. Execute trade (POST /paper-trading/execute)
3. Verify trade in history (GET /paper-trading/history)
4. Verify position in portfolio (GET /paper-trading/portfolio)
5. Verify database records (SQL queries)

---

## Rollback Plan

### If Phase 1 Fails

**Option 1: Revert code changes**
```bash
# Restore original paper_trading_controller.py
git checkout HEAD~1 src/paper_trading_controller.py

# Restore JSON files
cp data_backup_20251028/portfolio.json data/trades/
cp data_backup_20251028/paper_trades.json data/trades/

# Restart services
```

**Option 2: Keep database but fall back temporarily**
- Database remains intact with data
- Can retry migration after fixing issues
- No data loss

---

## Success Criteria

### Phase 1 Complete When:
- ✅ Portfolio loads from database
- ✅ Trades execute and save to database
- ✅ Trade history retrieves from database
- ✅ Positions track correctly in database
- ✅ Portfolio balance updates correctly
- ✅ No errors in logs
- ✅ All unit tests pass
- ✅ Full trading cycle works end-to-end

### Verification Checklist:
- [ ] `get_portfolio_state()` returns valid portfolio
- [ ] `insert_trade()` creates database records
- [ ] `add_portfolio_position()` creates position records
- [ ] Portfolio endpoint returns data from database
- [ ] Trade execution creates both trade and position records
- [ ] PostgreSQL queries show correct data
- [ ] System works without JSON files present
- [ ] Can execute 10 trades successfully
- [ ] Portfolio balance calculations are accurate

---

## Summary

**Estimated Time:** 2-3 hours

**Files to Create:**
1. `src/db/operations.py` - 10 functions for portfolio/trades (~300 lines)

**Files to Modify:**
1. `src/paper_trading_controller.py` - Replace 3 functions (load_portfolio, save_portfolio, append_trade_to_history)

**Risk Level:** Low
- ✅ Only affects one controller
- ✅ Other controllers unchanged
- ✅ Database already set up and tested
- ✅ Easy rollback via git
- ✅ Fresh start - no data migration complexity

**Next Phase (Future):**
- Phase 2: Price updater
- Phase 3: Events & Markets
- Phase 4: Trading signals

---

**Ready to implement?** Start with Step 1: Create `src/db/operations.py`
