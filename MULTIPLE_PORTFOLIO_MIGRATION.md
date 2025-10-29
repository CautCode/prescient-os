# Multiple Portfolio Migration Plan - Portfolio-Centric Architecture

## Executive Summary

This document provides an in-depth implementation guide for expanding Prescient OS to support multiple portfolios with independent trading strategies and P&L tracking. The Portfolio-Centric Architecture approach provides true isolation between portfolios, enabling:

- **Multiple concurrent strategies** running independently
- **Separate capital allocation** per portfolio
- **Independent P&L tracking** without cross-contamination
- **Strategy comparison** and A/B testing
- **Scalable architecture** for professional trading operations

**Implementation Complexity**: High
**Estimated Timeline**: 6 weeks
**Business Value**: Very High

---

## Table of Contents

1. [Current System Analysis](#current-system-analysis)
2. [Portfolio-Centric Architecture Overview](#portfolio-centric-architecture-overview)
3. [Database Migration Design](#database-migration-design)
4. [Database Operations Layer Changes](#database-operations-layer-changes)
5. [Controller Architecture Changes](#controller-architecture-changes)
6. [Price Updater Modifications](#price-updater-modifications)
7. [Trading Cycle Orchestration](#trading-cycle-orchestration)
8. [Migration Script Implementation](#migration-script-implementation)
9. [Testing Strategy](#testing-strategy)
10. [Deployment Plan](#deployment-plan)
11. [API Documentation](#api-documentation)
12. [Performance Considerations](#performance-considerations)
13. [Risk Management](#risk-management)

---

## Current System Analysis

### Architecture Constraints

The current system has the following limitations:

1. **Single Portfolio State** (`portfolio_state` table)
   - Single row with `id = 1`
   - Global balance: $10,000 initial
   - All trades share same capital pool
   - Location: `src/db/operations.py:32-68`

2. **No Portfolio Context in Data**
   - `portfolio_positions` table: no portfolio FK
   - `trades` table: no portfolio FK
   - `trading_signals` table: no portfolio FK
   - All queries return data without portfolio filtering

3. **Single Strategy Controller** (Port 8002)
   - Generates signals for all filtered markets
   - No strategy differentiation
   - Cannot run multiple strategies concurrently

4. **Global Price Updater**
   - Updates ALL open positions every 5 minutes
   - No portfolio-level filtering
   - Location: `src/paper_trading_controller.py:20-35`

### Current Trading Flow

```
Events Controller (8000)
    ↓ Export & Filter Events
Markets Controller (8001)
    ↓ Export & Filter Markets
Strategy Controller (8002)
    ↓ Generate Signals
Paper Trading Controller (8003)
    ↓ Execute Trades → Update Portfolio State (id=1)
    ↓ Price Updater (Background) → Update All Positions
Trading Controller (8004)
    ↓ Create Daily Snapshot
```

This flow must be adapted to support portfolio-specific execution while maintaining the same orchestration pattern.

---

## Portfolio-Centric Architecture Overview

### Core Concept

Replace the single `portfolio_state` table with a `portfolios` table that supports multiple portfolio instances. Each portfolio:

- Has its own balance and capital allocation
- Links to positions and trades via `portfolio_id` foreign key
- Has strategy configuration stored in JSONB field
- Operates independently from other portfolios
- Can be paused, archived, or rebalanced individually

### Key Design Principles

1. **True Isolation**: Each portfolio is completely independent
2. **Backward Compatibility**: Migrate existing data to "Default Portfolio"
3. **Strategy Flexibility**: Support both single controller and multi-controller approaches
4. **Performance**: Use database indexes for fast portfolio-filtered queries
5. **Scalability**: Design supports 100+ portfolios without architectural changes

---

## Database Migration Design

### Phase 1: Create New Tables

#### 1.1 Create `portfolios` Table

This is the central table that replaces `portfolio_state`:

```sql
-- Drop the old portfolio_state table (will be done after migration)
-- DROP TABLE portfolio_state;

CREATE TABLE portfolios (
    portfolio_id SERIAL PRIMARY KEY,

    -- Identity
    name VARCHAR(255) NOT NULL,
    description TEXT,
    strategy_type VARCHAR(100) NOT NULL,  -- 'momentum', 'mean_reversion', 'arbitrage', etc.

    -- Financial State
    initial_balance DECIMAL(15, 2) NOT NULL,
    current_balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) DEFAULT 0,
    total_profit_loss DECIMAL(15, 2) DEFAULT 0,
    trade_count INTEGER DEFAULT 0,

    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- 'active', 'paused', 'archived'
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),

    -- Strategy Configuration (flexible JSONB for strategy-specific params)
    strategy_config JSONB DEFAULT '{}'::jsonb,

    -- Risk Management
    max_position_size DECIMAL(15, 2),  -- Max $ per position
    max_total_exposure DECIMAL(15, 2),  -- Max $ invested across all positions
    max_positions INTEGER DEFAULT 20,  -- Max number of concurrent positions

    -- Performance Tracking (denormalized for fast queries)
    total_trades_executed INTEGER DEFAULT 0,
    total_winning_trades INTEGER DEFAULT 0,
    total_losing_trades INTEGER DEFAULT 0,
    avg_trade_pnl DECIMAL(15, 2) DEFAULT 0,
    max_drawdown DECIMAL(15, 2) DEFAULT 0,

    -- Metadata
    last_trade_at TIMESTAMP,
    last_price_update TIMESTAMP,

    UNIQUE(name)
);

-- Indexes for performance
CREATE INDEX idx_portfolios_status ON portfolios(status);
CREATE INDEX idx_portfolios_strategy_type ON portfolios(strategy_type);
CREATE INDEX idx_portfolios_status_strategy ON portfolios(status, strategy_type);
```

**Strategy Config Example**:

```json
{
    "min_confidence": 0.75,
    "max_position_size": 500,
    "market_types": ["politics", "crypto"],
    "min_liquidity": 50000,
    "min_volume": 100000,
    "risk_per_trade": 0.02,
    "stop_loss_percentage": 0.15,
    "take_profit_percentage": 0.25,
    "rebalance_threshold": 0.10
}
```

### Phase 2: Add `portfolio_id` Foreign Keys

#### 2.1 Modify `portfolio_positions`

```sql
-- Add portfolio_id column (nullable first for migration)
ALTER TABLE portfolio_positions
ADD COLUMN portfolio_id INTEGER;

-- Add foreign key constraint
ALTER TABLE portfolio_positions
ADD CONSTRAINT fk_portfolio_positions_portfolio
FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
ON DELETE CASCADE;

-- Create indexes for fast filtering
CREATE INDEX idx_portfolio_positions_portfolio_id
ON portfolio_positions(portfolio_id);

CREATE INDEX idx_portfolio_positions_portfolio_status
ON portfolio_positions(portfolio_id, status);

CREATE INDEX idx_portfolio_positions_portfolio_market
ON portfolio_positions(portfolio_id, market_id);

-- After migration, make NOT NULL
-- ALTER TABLE portfolio_positions ALTER COLUMN portfolio_id SET NOT NULL;
```

#### 2.2 Modify `trades`

```sql
-- Add portfolio_id column (nullable first for migration)
ALTER TABLE trades
ADD COLUMN portfolio_id INTEGER;

-- Add foreign key constraint
ALTER TABLE trades
ADD CONSTRAINT fk_trades_portfolio
FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
ON DELETE CASCADE;

-- Create indexes for analytics
CREATE INDEX idx_trades_portfolio_id
ON trades(portfolio_id);

CREATE INDEX idx_trades_portfolio_timestamp
ON trades(portfolio_id, timestamp);

CREATE INDEX idx_trades_portfolio_status
ON trades(portfolio_id, status);

-- After migration, make NOT NULL
-- ALTER TABLE trades ALTER COLUMN portfolio_id SET NOT NULL;
```

#### 2.3 Modify `trading_signals`

```sql
-- Add portfolio_id column (nullable for now)
ALTER TABLE trading_signals
ADD COLUMN portfolio_id INTEGER;

-- Add strategy_type for tracking which strategy generated the signal
ALTER TABLE trading_signals
ADD COLUMN strategy_type VARCHAR(100);

-- Add foreign key constraint
ALTER TABLE trading_signals
ADD CONSTRAINT fk_trading_signals_portfolio
FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
ON DELETE CASCADE;

-- Create indexes
CREATE INDEX idx_trading_signals_portfolio
ON trading_signals(portfolio_id);

CREATE INDEX idx_trading_signals_portfolio_executed
ON trading_signals(portfolio_id, executed);

CREATE INDEX idx_trading_signals_strategy
ON trading_signals(strategy_type);

-- After migration, can optionally make NOT NULL
-- ALTER TABLE trading_signals ALTER COLUMN portfolio_id SET NOT NULL;
```

#### 2.4 Modify `portfolio_history`

```sql
-- Add portfolio_id column
ALTER TABLE portfolio_history
ADD COLUMN portfolio_id INTEGER;

-- Add foreign key constraint
ALTER TABLE portfolio_history
ADD CONSTRAINT fk_portfolio_history_portfolio
FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
ON DELETE CASCADE;

-- Create indexes for time-series queries
CREATE INDEX idx_portfolio_history_portfolio_date
ON portfolio_history(portfolio_id, snapshot_date);

CREATE INDEX idx_portfolio_history_portfolio_timestamp
ON portfolio_history(portfolio_id, timestamp);

-- After migration, make NOT NULL
-- ALTER TABLE portfolio_history ALTER COLUMN portfolio_id SET NOT NULL;
```

### Phase 3: Additional Supporting Tables

#### 3.1 Create `portfolio_rebalancing_log`

Track capital movements between portfolios:

```sql
CREATE TABLE portfolio_rebalancing_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    from_portfolio_id INTEGER REFERENCES portfolios(portfolio_id),
    to_portfolio_id INTEGER REFERENCES portfolios(portfolio_id),
    amount DECIMAL(15, 2) NOT NULL,
    reason TEXT,
    executed_by VARCHAR(100),  -- 'system' or 'manual'

    CONSTRAINT positive_amount CHECK (amount > 0)
);

CREATE INDEX idx_rebalancing_from_portfolio ON portfolio_rebalancing_log(from_portfolio_id);
CREATE INDEX idx_rebalancing_to_portfolio ON portfolio_rebalancing_log(to_portfolio_id);
CREATE INDEX idx_rebalancing_timestamp ON portfolio_rebalancing_log(timestamp);
```

#### 3.2 Create `portfolio_performance_cache`

Cache expensive performance calculations:

```sql
CREATE TABLE portfolio_performance_cache (
    portfolio_id INTEGER PRIMARY KEY REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    calculated_at TIMESTAMP DEFAULT NOW(),

    -- Performance Metrics
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    win_rate DECIMAL(5, 2),
    avg_win DECIMAL(15, 2),
    avg_loss DECIMAL(15, 2),
    profit_factor DECIMAL(10, 4),
    max_consecutive_wins INTEGER,
    max_consecutive_losses INTEGER,

    -- Time-based Returns
    return_1d DECIMAL(10, 4),
    return_7d DECIMAL(10, 4),
    return_30d DECIMAL(10, 4),
    return_all_time DECIMAL(10, 4)
);
```

---

## Database Operations Layer Changes

All functions in `src/db/operations.py` need to be updated to support portfolio context.

### Pattern 1: Add Optional `portfolio_id` Parameter

For functions that currently operate globally, add optional `portfolio_id`:

```python
# OLD - operates on single portfolio
def get_portfolio_state() -> Dict:
    with get_db() as db:
        result = db.execute(text("""
            SELECT balance, total_invested, total_profit_loss, trade_count
            FROM portfolio_state WHERE id = 1
        """)).fetchone()
        # ...

# NEW - operates on specific or default portfolio
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
                   last_updated, strategy_config, max_position_size,
                   max_total_exposure, max_positions
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
            'max_position_size': float(result[13]) if result[13] else None,
            'max_total_exposure': float(result[14]) if result[14] else None,
            'max_positions': int(result[15]) if result[15] else 20
        }
```

### Pattern 2: Helper Function for Default Portfolio

```python
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
```

### Complete Function Updates

#### Portfolio Operations

```python
# ============================================================================
# PORTFOLIO OPERATIONS
# ============================================================================

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
                'max_position_size': 500
            },
            'max_position_size': 500,
            'max_total_exposure': 10000
        })
    """
    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO portfolios
            (name, description, strategy_type, initial_balance, current_balance,
             strategy_config, max_position_size, max_total_exposure, max_positions, status)
            VALUES (:name, :description, :strategy_type, :initial_balance, :current_balance,
                    CAST(:strategy_config AS jsonb), :max_position_size, :max_total_exposure,
                    :max_positions, 'active')
            RETURNING portfolio_id
        """), {
            'name': portfolio_data['name'],
            'description': portfolio_data.get('description', ''),
            'strategy_type': portfolio_data['strategy_type'],
            'initial_balance': portfolio_data['initial_balance'],
            'current_balance': portfolio_data.get('current_balance', portfolio_data['initial_balance']),
            'strategy_config': json.dumps(portfolio_data.get('strategy_config', {})),
            'max_position_size': portfolio_data.get('max_position_size'),
            'max_total_exposure': portfolio_data.get('max_total_exposure'),
            'max_positions': portfolio_data.get('max_positions', 20)
        })
        portfolio_id = result.scalar_one()
        db.commit()
        logger.info(f"Created portfolio {portfolio_id}: {portfolio_data['name']}")
        return int(portfolio_id)


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
                   last_updated, strategy_config
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
                'strategy_config': row[12] or {}
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
```

#### Position Operations

```python
def get_portfolio_positions(portfolio_id: int, status: str = 'open') -> List[Dict]:
    """
    Get positions for specific portfolio

    Args:
        portfolio_id: Portfolio to query
        status: Position status filter ('open', 'closed')

    Returns:
        List of position dictionaries
    """
    with get_db() as db:
        results = db.execute(text("""
            SELECT trade_id, market_id, market_question, action, amount,
                   entry_price, entry_timestamp, status, current_pnl,
                   realized_pnl, exit_price, exit_timestamp
            FROM portfolio_positions
            WHERE portfolio_id = :portfolio_id AND status = :status
            ORDER BY entry_timestamp DESC
        """), {'portfolio_id': portfolio_id, 'status': status}).fetchall()

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


def add_portfolio_position(position: Dict, portfolio_id: int):
    """
    Add position to specific portfolio

    Args:
        position: Position data dictionary
        portfolio_id: Portfolio to add position to
    """
    with get_db() as db:
        db.execute(text("""
            INSERT INTO portfolio_positions
            (portfolio_id, trade_id, market_id, market_question, action, amount,
             entry_price, entry_timestamp, status, current_pnl)
            VALUES (:portfolio_id, :trade_id, :market_id, :market_question, :action,
                    :amount, :entry_price, :entry_timestamp, :status, :current_pnl)
        """), {
            'portfolio_id': portfolio_id,
            'trade_id': position['trade_id'],
            'market_id': position['market_id'],
            'market_question': position['market_question'],
            'action': position['action'],
            'amount': position['amount'],
            'entry_price': position['entry_price'],
            'entry_timestamp': position['entry_timestamp'],
            'status': position['status'],
            'current_pnl': position.get('current_pnl', 0.0)
        })
        db.commit()
```

#### Trade Operations

```python
def insert_trade(trade: Dict, portfolio_id: int):
    """
    Insert trade for specific portfolio

    Args:
        trade: Trade data dictionary
        portfolio_id: Portfolio executing the trade
    """
    with get_db() as db:
        db.execute(text("""
            INSERT INTO trades
            (portfolio_id, trade_id, timestamp, market_id, market_question, action,
             amount, entry_price, confidence, reason, status, event_id, event_title,
             event_end_date, current_pnl, realized_pnl)
            VALUES (:portfolio_id, :trade_id, :timestamp, :market_id, :market_question,
                    :action, :amount, :entry_price, :confidence, :reason, :status,
                    :event_id, :event_title, :event_end_date, :current_pnl, :realized_pnl)
        """), {
            'portfolio_id': portfolio_id,
            **trade
        })
        db.commit()


def get_trades(portfolio_id: int = None, limit: int = None, status: str = None) -> List[Dict]:
    """
    Get trades with optional portfolio filter

    Args:
        portfolio_id: Filter by portfolio (None = all portfolios)
        limit: Max number of trades to return
        status: Filter by status

    Returns:
        List of trade dictionaries
    """
    with get_db() as db:
        query = """
            SELECT portfolio_id, trade_id, timestamp, market_id, market_question,
                   action, amount, entry_price, confidence, reason, status,
                   event_id, event_title, event_end_date, current_pnl, realized_pnl
            FROM trades
        """

        params = {}
        where_clauses = []

        if portfolio_id is not None:
            where_clauses.append("portfolio_id = :portfolio_id")
            params['portfolio_id'] = portfolio_id

        if status:
            where_clauses.append("status = :status")
            params['status'] = status

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

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
```

#### Signal Operations

```python
def insert_signal(signal: Dict, portfolio_id: int, strategy_type: str) -> int:
    """
    Insert signal for specific portfolio and strategy

    Args:
        signal: Signal data dictionary
        portfolio_id: Target portfolio
        strategy_type: Strategy that generated signal

    Returns:
        Inserted signal ID
    """
    with get_db() as db:
        result = db.execute(text("""
            INSERT INTO trading_signals
            (portfolio_id, strategy_type, timestamp, market_id, market_question,
             action, target_price, amount, confidence, reason, yes_price, no_price,
             market_liquidity, market_volume, event_id, event_title, event_end_date,
             executed, executed_at, trade_id)
            VALUES (:portfolio_id, :strategy_type, :timestamp, :market_id, :market_question,
                    :action, :target_price, :amount, :confidence, :reason, :yes_price,
                    :no_price, :market_liquidity, :market_volume, :event_id, :event_title,
                    :event_end_date, :executed, :executed_at, :trade_id)
            RETURNING id
        """), {
            'portfolio_id': portfolio_id,
            'strategy_type': strategy_type,
            **signal
        })
        inserted_id = result.scalar_one()
        db.commit()
        return int(inserted_id)


def get_current_signals(portfolio_id: int = None, executed: bool = False) -> List[Dict]:
    """
    Get signals with optional portfolio filter

    Args:
        portfolio_id: Filter by portfolio (None = all portfolios)
        executed: Filter by execution status

    Returns:
        List of signal dictionaries
    """
    with get_db() as db:
        query = """
            SELECT id, portfolio_id, strategy_type, timestamp, market_id, market_question,
                   action, target_price, amount, confidence, reason, yes_price, no_price,
                   market_liquidity, market_volume, event_id, event_title, event_end_date,
                   executed, executed_at, trade_id
            FROM trading_signals
        """

        params = {}
        where_clauses = []

        if portfolio_id is not None:
            where_clauses.append("portfolio_id = :portfolio_id")
            params['portfolio_id'] = portfolio_id

        where_clauses.append("executed = :executed")
        params['executed'] = executed

        query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY timestamp DESC"

        results = db.execute(text(query), params).fetchall()

        signals = []
        for row in results:
            signals.append({
                'id': int(row[0]),
                'portfolio_id': int(row[1]),
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

        return signals
```

---

## Controller Architecture Changes

### Strategy Controller Architecture Decision

**Decision Point**: Do we use one strategy controller with portfolio context, or multiple strategy controllers?

#### Option A: Single Strategy Controller with Portfolio Context (Simpler)

**Port 8002**: Strategy Controller

- Accepts `portfolio_id` parameter in all endpoints
- Loads strategy config from `portfolios.strategy_config` JSONB field
- Generates signals based on portfolio's strategy type
- Single codebase, easier to maintain

**Pros:**
- Simpler deployment (one process)
- Easier to maintain
- All strategies in one codebase
- Shared logic and utilities

**Cons:**
- All strategies in one file (can get large)
- Cannot independently restart strategies
- Less flexibility for different dependencies per strategy

#### Option B: Multiple Strategy Controllers (More Scalable)

**Port 8002**: Momentum Strategy Controller
**Port 8005**: Mean Reversion Strategy Controller
**Port 8006**: Arbitrage Strategy Controller
**Port 8007**: Hybrid Strategy Controller

Each controller:
- Accepts `portfolio_id` parameter
- Implements specific strategy logic
- Can have different dependencies
- Can be scaled independently

**Pros:**
- True separation of concerns
- Independent scaling and deployment
- Can run in parallel
- Different dependencies per strategy

**Cons:**
- More complex deployment
- Need to manage multiple processes
- More configuration

**Recommendation**: Start with Option A (single controller), migrate to Option B as needed.

### Paper Trading Controller Changes

The paper trading controller needs significant updates to support portfolio context.

#### Updated `execute_signals()` Function

```python
# src/paper_trading_controller.py

@app.get("/paper-trading/execute-signals")
async def execute_signals(portfolio_id: Optional[int] = None):
    """
    Execute signals for specific portfolio or all active portfolios

    Args:
        portfolio_id: Execute for specific portfolio (None = all active portfolios)

    Returns:
        Execution results with portfolio-specific details
    """
    try:
        logger.info("=== STARTING PAPER TRADING EXECUTION ===")

        # Determine which portfolios to execute
        if portfolio_id:
            portfolios = [get_portfolio_state(portfolio_id)]
            logger.info(f"Executing signals for portfolio {portfolio_id}: {portfolios[0]['name']}")
        else:
            portfolios = get_all_portfolios(status='active')
            logger.info(f"Executing signals for {len(portfolios)} active portfolios")

        all_results = []

        for portfolio in portfolios:
            pid = portfolio['portfolio_id']

            try:
                logger.info(f"Processing portfolio {pid}: {portfolio['name']}")

                # Step 1: Load unexecuted signals for this portfolio
                signals = get_current_signals(portfolio_id=pid, executed=False)
                logger.info(f"Portfolio {pid}: Found {len(signals)} unexecuted signals")

                if not signals:
                    all_results.append({
                        'portfolio_id': pid,
                        'portfolio_name': portfolio['name'],
                        'status': 'no_signals',
                        'executed_trades': 0,
                        'message': 'No signals to execute'
                    })
                    continue

                # Step 2: Execute trades for this portfolio
                executed_trades = []
                failed_trades = []

                for signal in signals:
                    trade_amount = signal.get('amount', 100)

                    # Check if portfolio has sufficient balance
                    if portfolio['current_balance'] < trade_amount:
                        logger.warning(f"Portfolio {pid}: Insufficient balance for signal {signal['id']}")
                        failed_trades.append({
                            'signal_id': signal['id'],
                            'reason': f"Insufficient balance: ${portfolio['current_balance']:.2f} < ${trade_amount}"
                        })
                        continue

                    # Check if portfolio would exceed max exposure
                    if portfolio.get('max_total_exposure'):
                        new_exposure = portfolio['total_invested'] + trade_amount
                        if new_exposure > portfolio['max_total_exposure']:
                            logger.warning(f"Portfolio {pid}: Would exceed max exposure")
                            failed_trades.append({
                                'signal_id': signal['id'],
                                'reason': f"Would exceed max exposure: ${new_exposure} > ${portfolio['max_total_exposure']}"
                            })
                            continue

                    # Check position size limit
                    if portfolio.get('max_position_size') and trade_amount > portfolio['max_position_size']:
                        logger.warning(f"Portfolio {pid}: Trade exceeds max position size")
                        failed_trades.append({
                            'signal_id': signal['id'],
                            'reason': f"Exceeds max position size: ${trade_amount} > ${portfolio['max_position_size']}"
                        })
                        continue

                    # Execute trade
                    trade = {
                        "trade_id": f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{signal['market_id']}_{pid}",
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

                    # Update portfolio state
                    portfolio['current_balance'] -= trade_amount
                    portfolio['total_invested'] += trade_amount
                    portfolio['trade_count'] += 1

                    # Save trade to database
                    insert_trade(trade, portfolio_id=pid)

                    # Add position
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
                    add_portfolio_position(position, portfolio_id=pid)

                    # Mark signal as executed
                    mark_signal_executed(signal['id'], trade['trade_id'])

                    executed_trades.append(trade)
                    logger.info(f"Portfolio {pid}: Executed trade {trade['trade_id']}")

                # Step 3: Save updated portfolio state
                update_portfolio(pid, {
                    'current_balance': portfolio['current_balance'],
                    'total_invested': portfolio['total_invested'],
                    'trade_count': portfolio['trade_count'],
                    'last_trade_at': datetime.now()
                })

                all_results.append({
                    'portfolio_id': pid,
                    'portfolio_name': portfolio['name'],
                    'status': 'completed',
                    'executed_trades': len(executed_trades),
                    'failed_trades': len(failed_trades),
                    'total_signals': len(signals),
                    'new_balance': portfolio['current_balance'],
                    'total_invested': portfolio['total_invested'],
                    'trades': executed_trades,
                    'failures': failed_trades
                })

                logger.info(f"Portfolio {pid}: Executed {len(executed_trades)} trades, {len(failed_trades)} failed")

            except Exception as portfolio_error:
                logger.error(f"Error executing portfolio {pid}: {portfolio_error}")
                all_results.append({
                    'portfolio_id': pid,
                    'portfolio_name': portfolio.get('name', 'Unknown'),
                    'status': 'error',
                    'error': str(portfolio_error)
                })

        # Summary
        total_executed = sum(r.get('executed_trades', 0) for r in all_results)
        total_failed = sum(r.get('failed_trades', 0) for r in all_results)

        logger.info("=== PAPER TRADING EXECUTION COMPLETED ===")
        logger.info(f"Portfolios processed: {len(all_results)}")
        logger.info(f"Total trades executed: {total_executed}")
        logger.info(f"Total trades failed: {total_failed}")

        return {
            "message": "Paper trading execution completed",
            "summary": {
                "portfolios_processed": len(all_results),
                "total_executed_trades": total_executed,
                "total_failed_trades": total_failed
            },
            "portfolio_results": all_results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Fatal error in paper trading execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### Updated `get_portfolio()` Function

```python
@app.get("/paper-trading/portfolio")
async def get_portfolio(portfolio_id: Optional[int] = None):
    """
    Get portfolio state for specific portfolio or all portfolios

    Args:
        portfolio_id: Specific portfolio ID (None = all active portfolios)

    Returns:
        Portfolio state with positions and P&L
    """
    try:
        if portfolio_id:
            # Get specific portfolio
            portfolio = get_portfolio_state(portfolio_id)
            positions = get_portfolio_positions(portfolio_id, status='open')

            # Update P&L with current prices
            try:
                market_data = get_markets(filters={'is_filtered': True})
                if market_data:
                    update_portfolio_pnl(portfolio, positions, market_data)
                    # Save updated P&L
                    update_portfolio(portfolio_id, {
                        'total_profit_loss': portfolio['total_profit_loss']
                    })
            except Exception as pnl_error:
                logger.debug(f"Could not update P&L: {pnl_error}")

            return {
                "message": "Portfolio retrieved",
                "portfolio": {
                    **portfolio,
                    'positions': positions
                },
                "summary": {
                    "total_value": portfolio['current_balance'] + portfolio['total_profit_loss'],
                    "open_positions": len(positions),
                    "total_invested": portfolio['total_invested'],
                    "unrealized_pnl": portfolio['total_profit_loss']
                },
                "timestamp": datetime.now().isoformat()
            }
        else:
            # Get all active portfolios
            portfolios = get_all_portfolios(status='active')

            portfolio_summaries = []
            for p in portfolios:
                pid = p['portfolio_id']
                positions = get_portfolio_positions(pid, status='open')

                portfolio_summaries.append({
                    'portfolio_id': pid,
                    'name': p['name'],
                    'strategy_type': p['strategy_type'],
                    'status': p['status'],
                    'current_balance': p['current_balance'],
                    'total_invested': p['total_invested'],
                    'total_profit_loss': p['total_profit_loss'],
                    'total_value': p['current_balance'] + p['total_profit_loss'],
                    'trade_count': p['trade_count'],
                    'open_positions': len(positions),
                    'last_updated': p['last_updated'].isoformat() if isinstance(p['last_updated'], datetime) else p['last_updated']
                })

            return {
                "message": "All portfolios retrieved",
                "portfolios": portfolio_summaries,
                "summary": {
                    "total_portfolios": len(portfolios),
                    "active_portfolios": len([p for p in portfolios if p['status'] == 'active']),
                    "total_value_all_portfolios": sum(p['total_value'] for p in portfolio_summaries),
                    "total_positions_all_portfolios": sum(p['open_positions'] for p in portfolio_summaries)
                },
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def update_portfolio_pnl(portfolio: Dict, positions: List[Dict], current_market_data: List[Dict]):
    """
    Update portfolio P&L based on current market prices

    Args:
        portfolio: Portfolio state dictionary (modified in-place)
        positions: List of open positions
        current_market_data: Current market price data
    """
    # Create market price lookup
    market_prices = {}
    for market in current_market_data:
        market_id = market.get('id') or market.get('market_id')
        if market_id and market.get('yes_price') is not None:
            market_prices[market_id] = {
                'yes_price': float(market['yes_price']),
                'no_price': float(market['no_price'])
            }

    # Calculate total P&L
    total_pnl = 0.0
    for position in positions:
        market_id = position['market_id']
        if market_id not in market_prices:
            continue

        current_prices = market_prices[market_id]
        entry_price = position['entry_price']
        amount = position['amount']
        action = position['action']

        # Get current price based on action
        if action == 'buy_yes':
            current_price = current_prices['yes_price']
        elif action == 'buy_no':
            current_price = current_prices['no_price']
        else:
            continue

        # Calculate P&L
        pnl = (current_price - entry_price) * amount
        position['current_pnl'] = round(pnl, 2)
        total_pnl += pnl

    portfolio['total_profit_loss'] = round(total_pnl, 2)
```

---

## Price Updater Modifications

The price updater background process needs to be updated to handle multiple portfolios.

### Updated Price Updater Logic

```python
# src/price_updater.py

def update_open_positions_prices(self):
    """
    Update prices for all open positions across all active portfolios
    Runs every 5 minutes (or configured interval)
    """
    try:
        logger.info("=== Starting price update cycle for all portfolios ===")

        # Get all active portfolios
        portfolios = get_all_portfolios(status='active')
        logger.info(f"Updating prices for {len(portfolios)} active portfolios")

        for portfolio in portfolios:
            portfolio_id = portfolio['portfolio_id']

            try:
                logger.debug(f"Updating portfolio {portfolio_id}: {portfolio['name']}")

                # Get open positions for this portfolio
                positions = get_portfolio_positions(portfolio_id, status='open')

                if not positions:
                    logger.debug(f"Portfolio {portfolio_id}: No open positions")
                    continue

                logger.info(f"Portfolio {portfolio_id}: Updating {len(positions)} positions")

                # Extract unique market IDs
                market_ids = list(set(p['market_id'] for p in positions))

                # Fetch current prices (batched)
                market_prices = self._fetch_market_prices_batch(market_ids)

                if not market_prices:
                    logger.warning(f"Portfolio {portfolio_id}: No market prices fetched")
                    continue

                # Update each position
                total_pnl = 0.0
                updated_count = 0

                for position in positions:
                    market_id = position['market_id']

                    if market_id not in market_prices:
                        logger.debug(f"Portfolio {portfolio_id}: No price data for market {market_id}")
                        continue

                    current_prices = market_prices[market_id]

                    # Get current price based on action
                    if position['action'] == 'buy_yes':
                        current_price = current_prices.get('yes_price')
                    elif position['action'] == 'buy_no':
                        current_price = current_prices.get('no_price')
                    else:
                        continue

                    if current_price is None:
                        continue

                    # Calculate P&L
                    entry_price = position['entry_price']
                    amount = position['amount']
                    position_pnl = (current_price - entry_price) * amount

                    # Update position in database
                    update_portfolio_position(
                        position['trade_id'],
                        {'current_pnl': round(position_pnl, 2)}
                    )

                    total_pnl += position_pnl
                    updated_count += 1

                    # Create market snapshot for history
                    insert_market_snapshot(market_id, {
                        'yes_price': current_prices.get('yes_price'),
                        'no_price': current_prices.get('no_price'),
                        'liquidity': current_prices.get('liquidity'),
                        'volume': current_prices.get('volume'),
                        'volume24hr': current_prices.get('volume24hr'),
                        'market_conviction': current_prices.get('market_conviction')
                    })

                # Update portfolio total P&L
                update_portfolio(portfolio_id, {
                    'total_profit_loss': round(total_pnl, 2),
                    'last_price_update': datetime.now()
                })

                logger.info(
                    f"Portfolio {portfolio_id}: Updated {updated_count} positions, "
                    f"total P&L: ${total_pnl:.2f}"
                )

            except Exception as portfolio_error:
                logger.error(f"Error updating portfolio {portfolio_id}: {portfolio_error}")
                # Continue with next portfolio
                continue

        logger.info("=== Price update cycle completed for all portfolios ===")

    except Exception as e:
        logger.error(f"Fatal error in price updater: {e}")
        # Don't crash the updater, log and continue


def _fetch_market_prices_batch(self, market_ids: List[str]) -> Dict[str, Dict]:
    """
    Fetch current prices for multiple markets (batched for efficiency)

    Args:
        market_ids: List of market IDs to fetch

    Returns:
        Dictionary mapping market_id to price data
    """
    market_prices = {}

    try:
        # Fetch markets from database (already has current prices from market controller)
        markets = get_markets(filters={'is_filtered': True})

        for market in markets:
            if market.get('id') in market_ids or market.get('market_id') in market_ids:
                market_id = market.get('id') or market.get('market_id')
                market_prices[market_id] = {
                    'yes_price': market.get('yes_price'),
                    'no_price': market.get('no_price'),
                    'liquidity': market.get('liquidity'),
                    'volume': market.get('volume'),
                    'volume24hr': market.get('volume24hr'),
                    'market_conviction': market.get('market_conviction')
                }

        # If we're missing prices, fall back to API fetch
        missing_ids = [mid for mid in market_ids if mid not in market_prices]

        if missing_ids:
            logger.debug(f"Fetching {len(missing_ids)} markets from API")
            for market_id in missing_ids:
                try:
                    # Fetch from Polymarket API
                    market_data = self._fetch_single_market(market_id)
                    if market_data:
                        market_prices[market_id] = market_data
                except Exception as fetch_error:
                    logger.warning(f"Could not fetch market {market_id}: {fetch_error}")

    except Exception as e:
        logger.error(f"Error fetching market prices: {e}")

    return market_prices
```

---

## Trading Cycle Orchestration

The trading controller needs to be updated to orchestrate portfolio-specific cycles.

### New Trading Controller Endpoints

```python
# src/trading_controller.py

@app.get("/trading/run-portfolio-cycle")
async def run_portfolio_cycle(
    portfolio_id: int,
    # Event filtering parameters
    event_min_liquidity: float = 10000,
    event_min_volume: float = 50000,
    # Market filtering parameters
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_market_conviction: Optional[float] = 0.5,
    max_market_conviction: Optional[float] = 0.6
):
    """
    Run trading cycle for specific portfolio

    Args:
        portfolio_id: Portfolio to run cycle for
        (other filtering parameters same as before)

    Returns:
        Cycle results for the portfolio
    """
    try:
        logger.info(f"=== STARTING TRADING CYCLE FOR PORTFOLIO {portfolio_id} ===")

        # Load portfolio
        portfolio = get_portfolio_state(portfolio_id)
        logger.info(f"Portfolio: {portfolio['name']} ({portfolio['strategy_type']})")

        # Check portfolio status
        if portfolio['status'] != 'active':
            raise HTTPException(
                status_code=400,
                detail=f"Portfolio {portfolio_id} is {portfolio['status']}, not active"
            )

        results = {
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "strategy_type": portfolio['strategy_type'],
            "cycle_started": datetime.now().isoformat(),
            "steps": [],
            "success": True
        }

        # Step 1: Export and filter events (shared across portfolios)
        logger.info("Step 1: Exporting and filtering events...")
        export_events_url = f"{EVENTS_API_BASE}/events/export-all-active-events-db"
        export_response = call_api(export_events_url)

        if not export_response:
            raise HTTPException(status_code=500, detail="Event export failed")

        results["steps"].append({
            "step": "1a",
            "name": "Export Events",
            "status": "completed",
            "details": export_response
        })

        # Filter events
        filter_events_url = f"{EVENTS_API_BASE}/events/filter-trading-candidates-db"
        event_params = f"min_liquidity={event_min_liquidity}&min_volume={event_min_volume}"
        filter_response = call_api(f"{filter_events_url}?{event_params}")

        if not filter_response:
            raise HTTPException(status_code=500, detail="Event filtering failed")

        results["steps"].append({
            "step": "1b",
            "name": "Filter Events",
            "status": "completed",
            "details": filter_response
        })

        # Step 2: Filter markets
        logger.info("Step 2: Filtering markets...")
        markets_url = f"{MARKETS_API_BASE}/markets/export-filtered-markets-db"
        market_params = f"min_liquidity={min_liquidity}&min_volume={min_volume}"
        if min_market_conviction:
            market_params += f"&min_market_conviction={min_market_conviction}"
        if max_market_conviction:
            market_params += f"&max_market_conviction={max_market_conviction}"

        markets_response = call_api(f"{markets_url}?{market_params}")

        if not markets_response:
            raise HTTPException(status_code=500, detail="Market filtering failed")

        results["steps"].append({
            "step": "2",
            "name": "Filter Markets",
            "status": "completed",
            "details": markets_response
        })

        # Step 3: Generate signals for this portfolio
        logger.info(f"Step 3: Generating signals for portfolio {portfolio_id}...")

        # Pass portfolio_id to strategy controller
        signals_url = f"{STRATEGY_API_BASE}/strategy/generate-signals?portfolio_id={portfolio_id}"
        signals_response = call_api(signals_url)

        if not signals_response:
            raise HTTPException(status_code=500, detail="Signal generation failed")

        results["steps"].append({
            "step": "3",
            "name": "Generate Signals",
            "status": "completed",
            "details": signals_response
        })

        # Step 4: Execute trades for this portfolio
        logger.info(f"Step 4: Executing trades for portfolio {portfolio_id}...")
        execute_url = f"{PAPER_TRADING_API_BASE}/paper-trading/execute-signals?portfolio_id={portfolio_id}"
        execute_response = call_api(execute_url)

        if not execute_response:
            raise HTTPException(status_code=500, detail="Trade execution failed")

        results["steps"].append({
            "step": "4",
            "name": "Execute Trades",
            "status": "completed",
            "details": execute_response
        })

        # Step 5: Create portfolio snapshot
        logger.info(f"Step 5: Creating snapshot for portfolio {portfolio_id}...")
        portfolio_url = f"{PAPER_TRADING_API_BASE}/paper-trading/portfolio?portfolio_id={portfolio_id}"
        portfolio_response = call_api(portfolio_url)

        if portfolio_response:
            create_daily_portfolio_snapshot(portfolio_response.get('portfolio', {}), portfolio_id)
            results["steps"].append({
                "step": "5",
                "name": "Portfolio Snapshot",
                "status": "completed",
                "details": portfolio_response.get('summary', {})
            })

        results["cycle_completed"] = datetime.now().isoformat()

        logger.info(f"=== TRADING CYCLE COMPLETED FOR PORTFOLIO {portfolio_id} ===")

        return {
            "message": f"Trading cycle completed for portfolio {portfolio_id}",
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in portfolio cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trading/run-all-portfolios")
async def run_all_portfolios(
    # Same filtering parameters as before
    event_min_liquidity: float = 10000,
    event_min_volume: float = 50000,
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_market_conviction: Optional[float] = 0.5,
    max_market_conviction: Optional[float] = 0.6
):
    """
    Run trading cycle for all active portfolios

    This is the main endpoint for automated trading that processes all portfolios

    Returns:
        Results for all portfolio cycles
    """
    try:
        logger.info("=== STARTING TRADING CYCLE FOR ALL PORTFOLIOS ===")

        # Get all active portfolios
        portfolios = get_all_portfolios(status='active')
        logger.info(f"Found {len(portfolios)} active portfolios")

        if not portfolios:
            return {
                "message": "No active portfolios found",
                "portfolios_processed": 0,
                "timestamp": datetime.now().isoformat()
            }

        # Run events/markets filtering once (shared across portfolios)
        logger.info("Running shared events/markets filtering...")

        # Export and filter events
        export_events_url = f"{EVENTS_API_BASE}/events/export-all-active-events-db"
        export_response = call_api(export_events_url)

        filter_events_url = f"{EVENTS_API_BASE}/events/filter-trading-candidates-db"
        event_params = f"min_liquidity={event_min_liquidity}&min_volume={event_min_volume}"
        filter_response = call_api(f"{filter_events_url}?{event_params}")

        # Filter markets
        markets_url = f"{MARKETS_API_BASE}/markets/export-filtered-markets-db"
        market_params = f"min_liquidity={min_liquidity}&min_volume={min_volume}"
        if min_market_conviction:
            market_params += f"&min_market_conviction={min_market_conviction}"
        if max_market_conviction:
            market_params += f"&max_market_conviction={max_market_conviction}"
        markets_response = call_api(f"{markets_url}?{market_params}")

        # Run portfolio-specific cycles
        portfolio_results = []

        for portfolio in portfolios:
            portfolio_id = portfolio['portfolio_id']

            try:
                logger.info(f"Processing portfolio {portfolio_id}: {portfolio['name']}")

                # Generate signals for this portfolio
                signals_url = f"{STRATEGY_API_BASE}/strategy/generate-signals?portfolio_id={portfolio_id}"
                signals_response = call_api(signals_url)

                # Execute trades for this portfolio
                execute_url = f"{PAPER_TRADING_API_BASE}/paper-trading/execute-signals?portfolio_id={portfolio_id}"
                execute_response = call_api(execute_url)

                # Create snapshot
                portfolio_url = f"{PAPER_TRADING_API_BASE}/paper-trading/portfolio?portfolio_id={portfolio_id}"
                portfolio_response = call_api(portfolio_url)

                if portfolio_response:
                    create_daily_portfolio_snapshot(
                        portfolio_response.get('portfolio', {}),
                        portfolio_id
                    )

                portfolio_results.append({
                    "portfolio_id": portfolio_id,
                    "portfolio_name": portfolio['name'],
                    "status": "success",
                    "signals_generated": signals_response.get('total_signals_generated', 0) if signals_response else 0,
                    "trades_executed": execute_response.get('summary', {}).get('executed_trades', 0) if execute_response else 0,
                    "current_balance": portfolio_response.get('summary', {}).get('total_value', 0) if portfolio_response else 0
                })

                logger.info(f"Portfolio {portfolio_id} cycle completed successfully")

            except Exception as portfolio_error:
                logger.error(f"Error processing portfolio {portfolio_id}: {portfolio_error}")
                portfolio_results.append({
                    "portfolio_id": portfolio_id,
                    "portfolio_name": portfolio['name'],
                    "status": "error",
                    "error": str(portfolio_error)
                })

        # Summary
        successful = len([r for r in portfolio_results if r['status'] == 'success'])
        failed = len([r for r in portfolio_results if r['status'] == 'error'])
        total_trades = sum(r.get('trades_executed', 0) for r in portfolio_results)

        logger.info("=== TRADING CYCLE COMPLETED FOR ALL PORTFOLIOS ===")
        logger.info(f"Successful: {successful}, Failed: {failed}, Total trades: {total_trades}")

        return {
            "message": "Trading cycle completed for all portfolios",
            "summary": {
                "total_portfolios": len(portfolios),
                "successful_portfolios": successful,
                "failed_portfolios": failed,
                "total_trades_executed": total_trades
            },
            "portfolio_results": portfolio_results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Fatal error in run_all_portfolios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def create_daily_portfolio_snapshot(portfolio_data: Dict, portfolio_id: int):
    """
    Create daily portfolio snapshot for specific portfolio

    Args:
        portfolio_data: Portfolio data dictionary
        portfolio_id: Portfolio ID
    """
    try:
        now = datetime.now()
        open_positions = len([
            p for p in portfolio_data.get('positions', [])
            if p.get('status') == 'open'
        ])

        snapshot = {
            'portfolio_id': portfolio_id,
            'snapshot_date': now.date(),
            'timestamp': now,
            'balance': portfolio_data.get('balance') or portfolio_data.get('current_balance', 0),
            'total_invested': portfolio_data.get('total_invested', 0),
            'total_profit_loss': portfolio_data.get('total_profit_loss', 0),
            'total_value': (
                portfolio_data.get('balance', 0) +
                portfolio_data.get('total_profit_loss', 0)
            ),
            'open_positions': open_positions,
            'trade_count': portfolio_data.get('trade_count', 0)
        }

        snapshot_id = insert_portfolio_history_snapshot(snapshot)
        logger.info(
            f"Created snapshot for portfolio {portfolio_id}: "
            f"id={snapshot_id}, value=${snapshot['total_value']:.2f}"
        )

    except Exception as e:
        logger.error(f"Error creating portfolio snapshot: {e}")
```

---

## Migration Script Implementation

**Recommended Approach**: Use the manual Python migration script below to migrate your database schema.

**After migration is complete**, you can optionally set up SQLAlchemy + Alembic for cleaner database operations and future migrations. See **[SQLALCHEMY_ALEMBIC_SETUP.md](SQLALCHEMY_ALEMBIC_SETUP.md)** for the complete guide.

### Why Manual Migration First?

1. **Faster**: Get the multi-portfolio system working quickly
2. **Less Duplication**: Don't write SQLAlchemy models twice (old + new schema)
3. **Lower Risk**: Separate the risky migration from the code refactor
4. **Progressive**: Migrate → Test → Then improve code quality with SQLAlchemy

---

## Manual Python Migration Script

Complete migration script to move from single to multiple portfolios:

```python
# scripts/migrate_to_multiple_portfolios.py

"""
Migration script to convert single portfolio system to multiple portfolio system

This script:
1. Creates the new portfolios table
2. Migrates existing portfolio_state data to a "Default Portfolio"
3. Updates all existing records with the default portfolio_id
4. Adds foreign key constraints
5. Drops the old portfolio_state table

IMPORTANT: Backup your database before running this script!
"""

import os
import sys
import logging
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from src.db.connection import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backup_database():
    """Create a database backup before migration"""
    logger.info("Creating database backup...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f"backup_before_portfolio_migration_{timestamp}.sql"

    # PostgreSQL backup command
    db_name = os.getenv('POSTGRES_DB', 'prescient_trading_db')
    os.system(f"pg_dump {db_name} > {backup_file}")

    logger.info(f"Backup created: {backup_file}")
    return backup_file


def create_portfolios_table():
    """Step 1: Create the new portfolios table"""
    logger.info("Step 1: Creating portfolios table...")

    with get_db() as db:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS portfolios (
                portfolio_id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                strategy_type VARCHAR(100) NOT NULL,
                initial_balance DECIMAL(15, 2) NOT NULL,
                current_balance DECIMAL(15, 2) NOT NULL,
                total_invested DECIMAL(15, 2) DEFAULT 0,
                total_profit_loss DECIMAL(15, 2) DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW(),
                last_updated TIMESTAMP DEFAULT NOW(),
                strategy_config JSONB DEFAULT '{}'::jsonb,
                max_position_size DECIMAL(15, 2),
                max_total_exposure DECIMAL(15, 2),
                max_positions INTEGER DEFAULT 20,
                total_trades_executed INTEGER DEFAULT 0,
                total_winning_trades INTEGER DEFAULT 0,
                total_losing_trades INTEGER DEFAULT 0,
                avg_trade_pnl DECIMAL(15, 2) DEFAULT 0,
                max_drawdown DECIMAL(15, 2) DEFAULT 0,
                last_trade_at TIMESTAMP,
                last_price_update TIMESTAMP,
                UNIQUE(name)
            )
        """))
        db.commit()

    logger.info("✓ Portfolios table created")


def create_indexes():
    """Step 2: Create indexes on portfolios table"""
    logger.info("Step 2: Creating indexes...")

    with get_db() as db:
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_portfolios_status
            ON portfolios(status)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_portfolios_strategy_type
            ON portfolios(strategy_type)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_portfolios_status_strategy
            ON portfolios(status, strategy_type)
        """))
        db.commit()

    logger.info("✓ Indexes created")


def migrate_portfolio_state():
    """Step 3: Migrate existing portfolio_state to portfolios table"""
    logger.info("Step 3: Migrating portfolio_state data...")

    with get_db() as db:
        # Get current portfolio state
        result = db.execute(text("""
            SELECT balance, total_invested, total_profit_loss, trade_count, created_at
            FROM portfolio_state
            WHERE id = 1
        """)).fetchone()

        if not result:
            logger.warning("No portfolio_state found, creating default portfolio")
            balance = 10000.0
            total_invested = 0.0
            total_profit_loss = 0.0
            trade_count = 0
            created_at = datetime.now()
        else:
            balance = float(result[0])
            total_invested = float(result[1])
            total_profit_loss = float(result[2])
            trade_count = int(result[3])
            created_at = result[4]

        # Insert as "Default Portfolio"
        result = db.execute(text("""
            INSERT INTO portfolios
            (name, description, strategy_type, initial_balance, current_balance,
             total_invested, total_profit_loss, trade_count, status, created_at)
            VALUES ('Default Portfolio', 'Migrated from single portfolio system',
                    'momentum', 10000.00, :balance, :total_invested, :total_profit_loss,
                    :trade_count, 'active', :created_at)
            RETURNING portfolio_id
        """), {
            'balance': balance,
            'total_invested': total_invested,
            'total_profit_loss': total_profit_loss,
            'trade_count': trade_count,
            'created_at': created_at
        })

        default_portfolio_id = result.scalar_one()
        db.commit()

        logger.info(f"✓ Default portfolio created with id={default_portfolio_id}")
        logger.info(f"   Balance: ${balance:.2f}")
        logger.info(f"   Total Invested: ${total_invested:.2f}")
        logger.info(f"   Total P&L: ${total_profit_loss:.2f}")
        logger.info(f"   Trade Count: {trade_count}")

        return int(default_portfolio_id)


def add_portfolio_id_columns():
    """Step 4: Add portfolio_id columns to existing tables"""
    logger.info("Step 4: Adding portfolio_id columns...")

    tables = [
        'portfolio_positions',
        'trades',
        'trading_signals',
        'portfolio_history'
    ]

    with get_db() as db:
        for table in tables:
            logger.info(f"   Adding portfolio_id to {table}...")
            db.execute(text(f"""
                ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS portfolio_id INTEGER
            """))

        # Add strategy_type to trading_signals
        logger.info("   Adding strategy_type to trading_signals...")
        db.execute(text("""
            ALTER TABLE trading_signals
            ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(100)
        """))

        db.commit()

    logger.info("✓ Columns added")


def update_existing_records(default_portfolio_id: int):
    """Step 5: Update all existing records with default portfolio_id"""
    logger.info(f"Step 5: Updating existing records with portfolio_id={default_portfolio_id}...")

    tables = [
        'portfolio_positions',
        'trades',
        'trading_signals',
        'portfolio_history'
    ]

    with get_db() as db:
        for table in tables:
            logger.info(f"   Updating {table}...")
            result = db.execute(text(f"""
                UPDATE {table}
                SET portfolio_id = :portfolio_id
                WHERE portfolio_id IS NULL
            """), {'portfolio_id': default_portfolio_id})

            updated_count = result.rowcount
            logger.info(f"   ✓ Updated {updated_count} rows in {table}")

        db.commit()

    logger.info("✓ All records updated")


def add_foreign_keys():
    """Step 6: Add foreign key constraints"""
    logger.info("Step 6: Adding foreign key constraints...")

    constraints = [
        ('portfolio_positions', 'fk_portfolio_positions_portfolio'),
        ('trades', 'fk_trades_portfolio'),
        ('trading_signals', 'fk_trading_signals_portfolio'),
        ('portfolio_history', 'fk_portfolio_history_portfolio')
    ]

    with get_db() as db:
        for table, constraint_name in constraints:
            logger.info(f"   Adding FK to {table}...")
            db.execute(text(f"""
                ALTER TABLE {table}
                ADD CONSTRAINT {constraint_name}
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id)
                ON DELETE CASCADE
            """))

        db.commit()

    logger.info("✓ Foreign keys added")


def add_table_indexes():
    """Step 7: Add indexes on portfolio_id columns"""
    logger.info("Step 7: Adding indexes on portfolio_id columns...")

    indexes = [
        ("portfolio_positions", "idx_portfolio_positions_portfolio_id", "portfolio_id"),
        ("portfolio_positions", "idx_portfolio_positions_portfolio_status", "portfolio_id, status"),
        ("portfolio_positions", "idx_portfolio_positions_portfolio_market", "portfolio_id, market_id"),
        ("trades", "idx_trades_portfolio_id", "portfolio_id"),
        ("trades", "idx_trades_portfolio_timestamp", "portfolio_id, timestamp"),
        ("trades", "idx_trades_portfolio_status", "portfolio_id, status"),
        ("trading_signals", "idx_trading_signals_portfolio", "portfolio_id"),
        ("trading_signals", "idx_trading_signals_portfolio_executed", "portfolio_id, executed"),
        ("trading_signals", "idx_trading_signals_strategy", "strategy_type"),
        ("portfolio_history", "idx_portfolio_history_portfolio_date", "portfolio_id, snapshot_date"),
        ("portfolio_history", "idx_portfolio_history_portfolio_timestamp", "portfolio_id, timestamp")
    ]

    with get_db() as db:
        for table, index_name, columns in indexes:
            logger.info(f"   Creating {index_name}...")
            db.execute(text(f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON {table}({columns})
            """))

        db.commit()

    logger.info("✓ Indexes created")


def make_portfolio_id_not_null():
    """Step 8: Make portfolio_id NOT NULL (optional - can be done later)"""
    logger.info("Step 8: Making portfolio_id NOT NULL...")

    tables = [
        'portfolio_positions',
        'trades',
        'portfolio_history'
    ]

    with get_db() as db:
        for table in tables:
            logger.info(f"   Updating {table}...")
            db.execute(text(f"""
                ALTER TABLE {table}
                ALTER COLUMN portfolio_id SET NOT NULL
            """))

        db.commit()

    logger.info("✓ Columns set to NOT NULL")


def drop_portfolio_state_table():
    """Step 9: Drop the old portfolio_state table"""
    logger.info("Step 9: Dropping portfolio_state table...")

    with get_db() as db:
        db.execute(text("DROP TABLE IF EXISTS portfolio_state"))
        db.commit()

    logger.info("✓ portfolio_state table dropped")


def verify_migration(default_portfolio_id: int):
    """Step 10: Verify migration was successful"""
    logger.info("Step 10: Verifying migration...")

    with get_db() as db:
        # Check portfolios table
        result = db.execute(text("""
            SELECT COUNT(*) FROM portfolios
        """)).scalar()
        logger.info(f"   Portfolios count: {result}")

        # Check each table has portfolio_id
        tables = ['portfolio_positions', 'trades', 'trading_signals', 'portfolio_history']
        for table in tables:
            result = db.execute(text(f"""
                SELECT COUNT(*) FROM {table} WHERE portfolio_id = :portfolio_id
            """), {'portfolio_id': default_portfolio_id}).scalar()
            logger.info(f"   {table} rows with portfolio_id={default_portfolio_id}: {result}")

        # Check no NULL portfolio_ids
        for table in ['portfolio_positions', 'trades', 'portfolio_history']:
            result = db.execute(text(f"""
                SELECT COUNT(*) FROM {table} WHERE portfolio_id IS NULL
            """)).scalar()
            if result > 0:
                logger.warning(f"   WARNING: {table} has {result} NULL portfolio_ids")
            else:
                logger.info(f"   ✓ {table} has no NULL portfolio_ids")

    logger.info("✓ Migration verification complete")


def main():
    """Run the complete migration"""
    logger.info("=" * 60)
    logger.info("PRESCIENT OS: MULTIPLE PORTFOLIO MIGRATION")
    logger.info("=" * 60)

    # Confirm with user
    print("\n⚠️  WARNING: This migration will make significant database changes")
    print("   Make sure you have backed up your database!")
    response = input("\nProceed with migration? (yes/no): ")

    if response.lower() != 'yes':
        logger.info("Migration cancelled by user")
        return

    try:
        # Create backup
        backup_file = backup_database()

        # Run migration steps
        create_portfolios_table()
        create_indexes()
        default_portfolio_id = migrate_portfolio_state()
        add_portfolio_id_columns()
        update_existing_records(default_portfolio_id)
        add_foreign_keys()
        add_table_indexes()
        make_portfolio_id_not_null()
        drop_portfolio_state_table()
        verify_migration(default_portfolio_id)

        logger.info("=" * 60)
        logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info(f"Default Portfolio ID: {default_portfolio_id}")
        logger.info(f"Backup File: {backup_file}")
        logger.info("\nNext steps:")
        logger.info("1. Test the system with the default portfolio")
        logger.info("2. Create additional portfolios using the new API endpoints")
        logger.info("3. Update your controllers to use portfolio_id parameters")

    except Exception as e:
        logger.error("=" * 60)
        logger.error("❌ MIGRATION FAILED")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error("\nRestore from backup:")
        logger.error(f"   psql {os.getenv('POSTGRES_DB', 'prescient_trading_db')} < {backup_file}")
        raise


if __name__ == "__main__":
    main()
```

---

## Testing Strategy

### Unit Testing

Create comprehensive unit tests for each component:

```python
# tests/test_portfolio_operations.py

import pytest
from src.db.operations import (
    create_portfolio,
    get_portfolio_state,
    get_all_portfolios,
    update_portfolio,
    add_portfolio_position,
    get_portfolio_positions,
    insert_trade
)


def test_create_portfolio():
    """Test portfolio creation"""
    portfolio_data = {
        'name': 'Test Portfolio',
        'description': 'Test description',
        'strategy_type': 'momentum',
        'initial_balance': 10000.00,
        'strategy_config': {'min_confidence': 0.75}
    }

    portfolio_id = create_portfolio(portfolio_data)
    assert portfolio_id > 0

    # Verify portfolio was created
    portfolio = get_portfolio_state(portfolio_id)
    assert portfolio['name'] == 'Test Portfolio'
    assert portfolio['initial_balance'] == 10000.00


def test_portfolio_isolation():
    """Test that portfolios are isolated from each other"""
    # Create two portfolios
    portfolio1_id = create_portfolio({
        'name': 'Portfolio 1',
        'strategy_type': 'momentum',
        'initial_balance': 10000.00
    })

    portfolio2_id = create_portfolio({
        'name': 'Portfolio 2',
        'strategy_type': 'mean_reversion',
        'initial_balance': 20000.00
    })

    # Add position to portfolio 1
    add_portfolio_position({
        'trade_id': 'test_trade_1',
        'market_id': 'market_1',
        'market_question': 'Test market?',
        'action': 'buy_yes',
        'amount': 100,
        'entry_price': 0.50,
        'entry_timestamp': '2025-01-01T00:00:00',
        'status': 'open',
        'current_pnl': 0
    }, portfolio1_id)

    # Verify portfolio 1 has position, portfolio 2 doesn't
    positions_1 = get_portfolio_positions(portfolio1_id, status='open')
    positions_2 = get_portfolio_positions(portfolio2_id, status='open')

    assert len(positions_1) == 1
    assert len(positions_2) == 0


def test_multiple_portfolio_queries():
    """Test querying across multiple portfolios"""
    # Create multiple portfolios
    for i in range(5):
        create_portfolio({
            'name': f'Test Portfolio {i}',
            'strategy_type': 'momentum',
            'initial_balance': 10000.00,
            'status': 'active'
        })

    # Get all active portfolios
    portfolios = get_all_portfolios(status='active')
    assert len(portfolios) >= 5


def test_portfolio_balance_updates():
    """Test that portfolio balance updates correctly after trades"""
    portfolio_id = create_portfolio({
        'name': 'Balance Test Portfolio',
        'strategy_type': 'momentum',
        'initial_balance': 10000.00
    })

    # Execute a trade
    trade = {
        'trade_id': 'balance_test_trade',
        'timestamp': '2025-01-01T00:00:00',
        'market_id': 'market_1',
        'market_question': 'Test?',
        'action': 'buy_yes',
        'amount': 500,
        'entry_price': 0.50,
        'confidence': 0.75,
        'reason': 'Test',
        'status': 'open',
        'event_id': 'event_1',
        'event_title': 'Test Event',
        'event_end_date': '2025-12-31',
        'current_pnl': 0,
        'realized_pnl': None
    }

    insert_trade(trade, portfolio_id)

    # Update portfolio balance
    update_portfolio(portfolio_id, {
        'current_balance': 9500.00,
        'total_invested': 500.00,
        'trade_count': 1
    })

    # Verify update
    portfolio = get_portfolio_state(portfolio_id)
    assert portfolio['current_balance'] == 9500.00
    assert portfolio['total_invested'] == 500.00
    assert portfolio['trade_count'] == 1
```

### Integration Testing

Test full trading cycle with multiple portfolios:

```python
# tests/test_multiple_portfolio_trading_cycle.py

import pytest
import requests

BASE_URL = "http://localhost:8004"


def test_full_cycle_multiple_portfolios():
    """Test complete trading cycle with multiple portfolios"""

    # Step 1: Create test portfolios
    portfolio_ids = []
    for i, strategy in enumerate(['momentum', 'mean_reversion']):
        response = requests.post(f"{BASE_URL}/portfolios/create", json={
            'name': f'Test {strategy.title()} Portfolio',
            'strategy_type': strategy,
            'initial_balance': 10000.00,
            'strategy_config': {
                'min_confidence': 0.70 + (i * 0.05)
            }
        })
        assert response.status_code == 200
        portfolio_ids.append(response.json()['portfolio_id'])

    # Step 2: Run trading cycle for all portfolios
    response = requests.get(f"{BASE_URL}/trading/run-all-portfolios")
    assert response.status_code == 200
    result = response.json()

    # Verify both portfolios were processed
    assert result['summary']['portfolios_processed'] == 2

    # Step 3: Check each portfolio independently
    for portfolio_id in portfolio_ids:
        response = requests.get(
            f"http://localhost:8003/paper-trading/portfolio?portfolio_id={portfolio_id}"
        )
        assert response.status_code == 200
        portfolio = response.json()['portfolio']

        # Verify portfolio data is independent
        assert portfolio['portfolio_id'] == portfolio_id


def test_portfolio_isolation_during_execution():
    """Test that portfolios don't interfere with each other during execution"""

    # Create two portfolios with different balances
    portfolio1 = requests.post(f"{BASE_URL}/portfolios/create", json={
        'name': 'High Balance Portfolio',
        'strategy_type': 'momentum',
        'initial_balance': 100000.00
    }).json()

    portfolio2 = requests.post(f"{BASE_URL}/portfolios/create", json={
        'name': 'Low Balance Portfolio',
        'strategy_type': 'momentum',
        'initial_balance': 1000.00
    }).json()

    # Run cycle for both
    response = requests.get(f"{BASE_URL}/trading/run-all-portfolios")
    assert response.status_code == 200

    # Check that low balance portfolio didn't use high balance portfolio's money
    portfolio2_state = requests.get(
        f"http://localhost:8003/paper-trading/portfolio?portfolio_id={portfolio2['portfolio_id']}"
    ).json()

    # Balance should still be around 1000 (minus any small trades)
    assert portfolio2_state['portfolio']['current_balance'] < 1100
```

### Performance Testing

Test system performance with many portfolios:

```python
# tests/test_portfolio_performance.py

import pytest
import time
import requests


def test_100_portfolio_price_update_performance():
    """Test that price updates can handle 100 portfolios within reasonable time"""

    # Create 100 portfolios (or use existing)
    portfolio_count = 100

    # Trigger price update
    start_time = time.time()
    response = requests.get("http://localhost:8003/paper-trading/update-prices")
    elapsed = time.time() - start_time

    # Should complete within 30 seconds for 100 portfolios
    assert elapsed < 30.0
    assert response.status_code == 200


def test_concurrent_portfolio_cycles():
    """Test running multiple portfolio cycles concurrently"""

    import concurrent.futures

    portfolio_ids = [1, 2, 3, 4, 5]

    def run_cycle(portfolio_id):
        response = requests.get(
            f"http://localhost:8004/trading/run-portfolio-cycle?portfolio_id={portfolio_id}"
        )
        return response.status_code == 200

    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(run_cycle, portfolio_ids))
    elapsed = time.time() - start_time

    # All should succeed
    assert all(results)

    # Should not take more than 2x single cycle time
    assert elapsed < 120.0  # Assuming single cycle takes ~60s
```

---

## Deployment Plan

### Phase 1: Development (Week 1-2)

**Week 1: Database Layer**
- Day 1-2: Create migration script, test on dev database
- Day 3-4: Update `src/db/operations.py` with new functions
- Day 5: Unit testing for all database operations

**Week 2: Core Controllers**
- Day 1-2: Update paper trading controller
- Day 3-4: Update price updater
- Day 5: Integration testing

### Phase 2: Controllers & Orchestration (Week 3-4)

**Week 3: Trading Orchestration**
- Day 1-2: Update trading controller with portfolio endpoints
- Day 3-4: Add portfolio management endpoints
- Day 5: End-to-end testing

**Week 4: Strategy Layer**
- Day 1-3: Modify strategy controller for portfolio context
- Day 4-5: Testing with multiple portfolios

### Phase 3: Testing & Validation (Week 5)

**Week 5: Comprehensive Testing**
- Day 1-2: Unit testing all components
- Day 3: Integration testing full cycles
- Day 4: Performance testing with 10+ portfolios
- Day 5: Bug fixes and optimization

### Phase 4: Production Deployment (Week 6)

**Week 6: Deployment**
- Day 1: Final testing in staging environment
- Day 2: Run migration script on production database (with backup!)
- Day 3: Deploy updated controllers
- Day 4: Monitor system, create first new portfolios
- Day 5: Documentation and training

### Rollback Plan

If issues occur during deployment:

1. **Stop all controllers** to prevent data corruption
2. **Restore database** from backup:
   ```bash
   psql prescient_trading_db < backup_before_portfolio_migration_YYYYMMDD_HHMMSS.sql
   ```
3. **Revert code** to previous version
4. **Restart controllers** with old code
5. **Investigate** the issue before re-attempting

---

## API Documentation

### Portfolio Management Endpoints

#### Create Portfolio
```
POST /portfolios/create
Content-Type: application/json

{
    "name": "Aggressive Momentum",
    "description": "High-risk momentum strategy",
    "strategy_type": "momentum",
    "initial_balance": 50000.00,
    "strategy_config": {
        "min_confidence": 0.80,
        "max_position_size": 1000
    },
    "max_position_size": 1000,
    "max_total_exposure": 20000
}

Response:
{
    "portfolio_id": 3,
    "message": "Portfolio created successfully"
}
```

#### Get Portfolio
```
GET /paper-trading/portfolio?portfolio_id=1

Response:
{
    "message": "Portfolio retrieved",
    "portfolio": {
        "portfolio_id": 1,
        "name": "Default Portfolio",
        "strategy_type": "momentum",
        "current_balance": 9500.00,
        "total_invested": 500.00,
        "total_profit_loss": 50.00,
        "positions": [...]
    },
    "summary": {
        "total_value": 10050.00,
        "open_positions": 5,
        "unrealized_pnl": 50.00
    }
}
```

#### List All Portfolios
```
GET /paper-trading/portfolio

Response:
{
    "message": "All portfolios retrieved",
    "portfolios": [
        {
            "portfolio_id": 1,
            "name": "Default Portfolio",
            "strategy_type": "momentum",
            "total_value": 10050.00,
            ...
        },
        {
            "portfolio_id": 2,
            "name": "Conservative",
            "strategy_type": "mean_reversion",
            "total_value": 20300.00,
            ...
        }
    ],
    "summary": {
        "total_portfolios": 2,
        "total_value_all_portfolios": 30350.00
    }
}
```

#### Update Portfolio
```
PATCH /portfolios/{portfolio_id}
Content-Type: application/json

{
    "status": "paused",
    "max_total_exposure": 15000
}

Response:
{
    "message": "Portfolio updated successfully"
}
```

#### Run Portfolio Cycle
```
GET /trading/run-portfolio-cycle?portfolio_id=1

Response:
{
    "message": "Trading cycle completed for portfolio 1",
    "results": {
        "portfolio_id": 1,
        "portfolio_name": "Default Portfolio",
        "steps": [...],
        "success": true
    }
}
```

#### Run All Portfolios
```
GET /trading/run-all-portfolios

Response:
{
    "message": "Trading cycle completed for all portfolios",
    "summary": {
        "total_portfolios": 3,
        "successful_portfolios": 3,
        "total_trades_executed": 12
    },
    "portfolio_results": [...]
}
```

---

## Performance Considerations

### Database Query Optimization

1. **Use Indexes**: All portfolio_id foreign keys have indexes
2. **Batch Operations**: Price updater fetches prices in batches
3. **Connection Pooling**: SQLAlchemy manages DB connection pool
4. **Query Filtering**: Always filter by portfolio_id to use indexes

### Scaling Guidelines

| Portfolios | Positions/Portfolio | Price Update Time | Recommended Hardware |
|------------|---------------------|-------------------|----------------------|
| 1-10       | 20-50               | < 10 seconds      | 2 CPU, 4GB RAM       |
| 10-50      | 20-50               | < 30 seconds      | 4 CPU, 8GB RAM       |
| 50-100     | 20-50               | < 60 seconds      | 8 CPU, 16GB RAM      |
| 100+       | 20-50               | < 120 seconds     | 16 CPU, 32GB RAM     |

### Monitoring

Key metrics to monitor:

1. **Price Update Cycle Time**: Should complete within 5-minute interval
2. **Database Query Time**: Portfolio queries should be < 100ms
3. **Trade Execution Time**: Should complete within 30 seconds per portfolio
4. **Memory Usage**: Should not grow unbounded (check for leaks)

---

## Risk Management

### Cross-Portfolio Risks

1. **Market Position Limits**: Implement global market position tracking
   ```python
   def check_global_market_exposure(market_id: str) -> Dict:
       """Check total exposure across all portfolios for a market"""
       with get_db() as db:
           result = db.execute(text("""
               SELECT COUNT(*), SUM(amount)
               FROM portfolio_positions
               WHERE market_id = :market_id AND status = 'open'
           """), {'market_id': market_id}).fetchone()

           return {
               'total_positions': result[0],
               'total_amount': float(result[1]) if result[1] else 0
           }
   ```

2. **API Rate Limiting**: Track API calls across all portfolios
3. **Capital Limits**: Ensure total capital doesn't exceed available funds

### Portfolio-Level Risk Management

Each portfolio enforces:
- `max_position_size`: Maximum $ per position
- `max_total_exposure`: Maximum total $ invested
- `max_positions`: Maximum number of open positions

### Emergency Controls

```python
def pause_all_portfolios(reason: str):
    """Emergency stop - pause all portfolios"""
    with get_db() as db:
        db.execute(text("""
            UPDATE portfolios
            SET status = 'paused'
            WHERE status = 'active'
        """))
        db.commit()
    logger.warning(f"ALL PORTFOLIOS PAUSED: {reason}")


def reactivate_portfolio(portfolio_id: int):
    """Reactivate a paused portfolio after review"""
    update_portfolio(portfolio_id, {'status': 'active'})
```

---

## Conclusion

This migration plan provides a complete roadmap for implementing the Portfolio-Centric Architecture in Prescient OS. The approach delivers:

✅ **True portfolio isolation** with separate capital and P&L
✅ **Scalable architecture** supporting 100+ portfolios
✅ **Backward compatibility** via migration script
✅ **Professional-grade** trading system design
✅ **Clear implementation** with code examples

**Success Criteria:**
- Zero data loss during migration
- All existing functionality preserved
- Ability to create and run multiple portfolios independently
- Price updates complete within 5-minute window for all portfolios
- Clean separation between portfolio strategies

**Next Steps After Implementation:**
1. Create additional strategy controllers (mean reversion, arbitrage)
2. Implement advanced portfolio analytics dashboard
3. Add automated portfolio rebalancing
4. Implement machine learning for strategy optimization
5. Add backtesting framework for strategy validation

---

*Document Version: 1.0*
*Last Updated: 2025-10-28*
*Implementation Approach: Portfolio-Centric Architecture*
*Estimated Implementation Time: 6 weeks*
*Complexity Level: High*
*Business Value: Very High*
