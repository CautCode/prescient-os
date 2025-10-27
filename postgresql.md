# PostgreSQL Migration Plan for Prescient OS

## Overview
This document outlines a phased approach to migrate the Prescient OS trading system from JSON file-based storage to PostgreSQL database. The migration will be done incrementally to minimize risk and maintain system functionality throughout the process.

---

## Current System Analysis

### Data Storage Patterns
Currently, the system uses JSON files for all data persistence:

1. **Events Data** (`data/events/`)
   - `raw_events_backup.json` - All active events from Polymarket API
   - `filtered_events.json` - Events filtered for trading viability

2. **Markets Data** (`data/markets/`)
   - `filtered_markets.json` - Markets filtered from events with detailed API data

3. **Trading Signals** (`data/trades/`)
   - `current_signals.json` - Current trading signals (OVERWRITE mode)
   - Signal archives in `data/history/signals_archive_YYYY-MM.json` (APPEND mode)

4. **Portfolio & Trades** (`data/trades/`)
   - `portfolio.json` - Current portfolio state (OVERWRITE mode)
   - `paper_trades.json` - Complete trade history (APPEND mode)

5. **Historical Data** (`data/history/`)
   - `portfolio_history.json` - Daily portfolio snapshots (APPEND mode)
   - `signals_archive_YYYY-MM.json` - Monthly signal archives (APPEND mode)

### Key Data Flows
1. Events Controller ’ Market Controller ’ Strategy Controller ’ Paper Trading Controller
2. Trading Controller orchestrates the full cycle
3. Data persistence happens at each stage with JSON files

---

## Migration Strategy: Phased Approach

### Phase 0: Preparation (Week 1)
**Goal**: Set up infrastructure without changing application code

#### Tasks:
1. **Install PostgreSQL**
   ```bash
   # Windows (using Chocolatey)
   choco install postgresql

   # Or download installer from postgresql.org
   ```

2. **Create Database and User**
   ```sql
   CREATE DATABASE prescient_os;
   CREATE USER prescient_user WITH PASSWORD 'your_secure_password';
   GRANT ALL PRIVILEGES ON DATABASE prescient_os TO prescient_user;
   ```

3. **Install Python Dependencies**
   ```bash
   pip install psycopg2-binary sqlalchemy alembic
   ```

4. **Create Database Schema File** (`src/db/schema.sql`)
   - See detailed schema below

5. **Create SQLAlchemy Models** (`src/db/models.py`)
   - ORM models for all tables

6. **Create Database Connection Manager** (`src/db/connection.py`)
   - Connection pooling
   - Environment variable configuration

7. **Set Up Alembic for Migrations**
   ```bash
   alembic init alembic
   ```

#### Deliverables:
- PostgreSQL installed and running
- Database created with schema
- Python database libraries installed
- Database models defined
- Connection manager ready

---

### Phase 1: Parallel Write - Trades & Portfolio (Week 2)
**Goal**: Start writing to PostgreSQL alongside JSON files, with zero risk

#### Why Start Here:
- Trade history and portfolio are the most critical data (business value)
- APPEND-only pattern for trades makes migration safer
- Portfolio is single-record, simple to sync
- No impact on data pipeline if database fails (JSON is still primary)

#### Implementation:

1. **Modify `paper_trading_controller.py`**
   - Add database operations alongside existing JSON operations
   - If database write fails, log error but continue (JSON is still source of truth)
   - Functions to modify:
     - `save_portfolio()` - Write to both JSON and DB
     - `append_trade_to_history()` - Write to both JSON and DB
     - `load_portfolio()` - Still read from JSON (for now)

2. **Tables Involved:**
   ```sql
   - portfolio_snapshots (timestamped portfolio states)
   - trades (all executed trades)
   ```

3. **Testing:**
   - Run full trading cycle
   - Verify data appears in both JSON and PostgreSQL
   - Verify system works even if database is offline

#### Success Criteria:
- Trades written to both JSON and PostgreSQL
- Portfolio updates written to both locations
- System continues working if database fails
- 100% data consistency between JSON and DB

---

### Phase 2: Parallel Write - Historical Data (Week 3)
**Goal**: Add historical tracking to PostgreSQL

#### Implementation:

1. **Modify `trading_controller.py`**
   - `create_daily_portfolio_snapshot()` - Write to both JSON and DB
   - `archive_current_signals()` - Write to both JSON and DB

2. **Tables Involved:**
   ```sql
   - portfolio_history (daily snapshots)
   - signal_archives (monthly signal archives)
   ```

3. **Backfill Historical Data (Optional):**
   ```python
   # Script: scripts/backfill_history.py
   # Read existing JSON history files and import to PostgreSQL
   ```

#### Success Criteria:
- Historical data written to both locations
- Backfill script successfully imports existing history
- No performance degradation

---

### Phase 3: Parallel Write - Trading Signals (Week 4)
**Goal**: Migrate current trading signals to database

#### Implementation:

1. **Modify `trading_strategy_controller.py`**
   - `generate_signals()` - Write signals to both JSON and DB
   - Keep JSON as primary read source for now

2. **Tables Involved:**
   ```sql
   - trading_signals (current signals with metadata)
   ```

3. **Add Signal Lifecycle Tracking:**
   - Track when signals are generated
   - Track when signals are executed
   - Link signals to executed trades

#### Success Criteria:
- Signals written to both JSON and PostgreSQL
- Signal-to-trade linkage working
- Signal history queryable in database

---

### Phase 4: Parallel Write - Markets & Events (Week 5)
**Goal**: Store filtered markets and events in database

#### Why Last for Writes:
- Largest data volume
- Frequently overwritten (less critical to persist long-term)
- Primary value is in the current state, not history

#### Implementation:

1. **Modify `market_controller.py`**
   - `export_filtered_markets_json()` - Write to both JSON and DB
   - Store market snapshots with timestamps

2. **Modify `events_controller.py`**
   - `export_all_active_events_json()` - Write to both JSON and DB (optional)
   - `filter_trading_candidates_json()` - Write to both JSON and DB

3. **Tables Involved:**
   ```sql
   - events (filtered events)
   - markets (filtered markets with metadata)
   - market_snapshots (time-series market data)
   ```

4. **Optimization Considerations:**
   - Events and markets have large payloads
   - Consider storing full JSON in JSONB column vs normalized tables
   - Add indexes on frequently queried fields (market_id, event_id, liquidity, volume)

#### Success Criteria:
- Markets and events written to both locations
- Time-series market data captured
- Query performance acceptable (<100ms for common queries)

---

### Phase 5: Switch to Database Reads (Week 6)
**Goal**: Gradually shift from reading JSON to reading PostgreSQL

#### Approach (Per Controller):
1. Add feature flag: `USE_DATABASE_READ = os.getenv('USE_DATABASE_READ', 'false').lower() == 'true'`
2. Modify load functions to check flag:
   ```python
   if USE_DATABASE_READ:
       return load_from_database()
   else:
       return load_from_json()
   ```
3. Test with flag enabled
4. Once stable, make database the default, keep JSON as fallback

#### Implementation Order:
1. **Portfolio reads** (most critical, single record, simple)
2. **Trade history reads** (read-only, append-only, safe)
3. **Signal reads** (current signals, small dataset)
4. **Market/Event reads** (largest dataset, test performance)

#### Success Criteria:
- All controllers successfully read from database
- Performance meets or exceeds JSON reads
- Fallback to JSON works if database unavailable

---

### Phase 6: Remove JSON Writes (Week 7)
**Goal**: Clean up dual-write code, make PostgreSQL primary

#### Implementation:
1. Remove JSON write operations (keep read as backup)
2. Update all controllers to only write to database
3. Add comprehensive error handling
4. Add database health checks to `/trading/status` endpoint

#### Migration Safety Net:
- Keep JSON read capability for 2 weeks as emergency fallback
- Create database backup script that exports to JSON format
- Monitor system stability

#### Success Criteria:
- Only writing to PostgreSQL
- System stable for 1 week
- Backup/restore procedures tested
- Database monitoring in place

---

### Phase 7: Deprecate JSON Storage (Week 8)
**Goal**: Fully commit to PostgreSQL, remove legacy code

#### Implementation:
1. Remove all JSON read/write code
2. Remove `data/` directory references
3. Update documentation
4. Archive existing JSON files for audit trail

#### Success Criteria:
- Zero JSON file operations in codebase
- All data flows through PostgreSQL
- Documentation updated
- Legacy data archived

---

## Detailed Database Schema

### Core Tables

```sql
-- Portfolio Management
CREATE TABLE portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_snapshots_timestamp ON portfolio_snapshots(timestamp DESC);

-- Current portfolio state (single row, updated)
CREATE TABLE portfolio_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    CONSTRAINT single_portfolio CHECK (id = 1)
);

-- Portfolio positions (open trades)
CREATE TABLE portfolio_positions (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) UNIQUE NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL, -- 'buy_yes' or 'buy_no'
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 6) NOT NULL,
    entry_timestamp TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL, -- 'open', 'closed'
    current_pnl DECIMAL(15, 2),
    realized_pnl DECIMAL(15, 2),
    exit_price DECIMAL(10, 6),
    exit_timestamp TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_positions_market_id ON portfolio_positions(market_id);
CREATE INDEX idx_positions_status ON portfolio_positions(status);

-- Trade History (append-only)
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(255) UNIQUE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    entry_price DECIMAL(10, 6) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    reason TEXT,
    status VARCHAR(50) NOT NULL,
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    current_pnl DECIMAL(15, 2),
    realized_pnl DECIMAL(15, 2),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_market_id ON trades(market_id);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX idx_trades_status ON trades(status);

-- Trading Signals
CREATE TABLE trading_signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    market_id VARCHAR(255) NOT NULL,
    market_question TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    target_price DECIMAL(10, 6) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL,
    reason TEXT,
    yes_price DECIMAL(10, 6) NOT NULL,
    no_price DECIMAL(10, 6) NOT NULL,
    market_liquidity DECIMAL(15, 2),
    market_volume DECIMAL(15, 2),
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP,
    trade_id VARCHAR(255) REFERENCES trades(trade_id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signals_market_id ON trading_signals(market_id);
CREATE INDEX idx_signals_timestamp ON trading_signals(timestamp DESC);
CREATE INDEX idx_signals_executed ON trading_signals(executed);

-- Signal Archives (monthly archives)
CREATE TABLE signal_archives (
    id SERIAL PRIMARY KEY,
    archived_at TIMESTAMP NOT NULL,
    archive_month VARCHAR(7) NOT NULL, -- 'YYYY-MM'
    signals_count INTEGER NOT NULL,
    signals_data JSONB NOT NULL, -- Store full signals array
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signal_archives_month ON signal_archives(archive_month);

-- Events (filtered events)
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    slug VARCHAR(500),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    days_until_end INTEGER,
    event_data JSONB NOT NULL, -- Store full event JSON
    is_filtered BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_event_id ON events(event_id);
CREATE INDEX idx_events_liquidity ON events(liquidity);
CREATE INDEX idx_events_volume ON events(volume);
CREATE INDEX idx_events_end_date ON events(end_date);

-- Markets (filtered markets)
CREATE TABLE markets (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) UNIQUE NOT NULL,
    question TEXT NOT NULL,
    event_id VARCHAR(255),
    event_title TEXT,
    event_end_date TIMESTAMP,
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    yes_price DECIMAL(10, 6),
    no_price DECIMAL(10, 6),
    market_conviction DECIMAL(10, 6),
    market_data JSONB NOT NULL, -- Store full market JSON
    is_filtered BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_markets_market_id ON markets(market_id);
CREATE INDEX idx_markets_event_id ON markets(event_id);
CREATE INDEX idx_markets_liquidity ON markets(liquidity);
CREATE INDEX idx_markets_volume ON markets(volume);

-- Market Snapshots (time-series market data)
CREATE TABLE market_snapshots (
    id SERIAL PRIMARY KEY,
    market_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    yes_price DECIMAL(10, 6),
    no_price DECIMAL(10, 6),
    liquidity DECIMAL(15, 2),
    volume DECIMAL(15, 2),
    volume24hr DECIMAL(15, 2),
    market_conviction DECIMAL(10, 6),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_snapshots_market_id ON market_snapshots(market_id);
CREATE INDEX idx_market_snapshots_timestamp ON market_snapshots(timestamp DESC);

-- Portfolio History (daily snapshots)
CREATE TABLE portfolio_history (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    total_invested DECIMAL(15, 2) NOT NULL,
    total_profit_loss DECIMAL(15, 2) NOT NULL,
    total_value DECIMAL(15, 2) NOT NULL,
    open_positions INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_history_date ON portfolio_history(snapshot_date DESC);

-- System Metadata
CREATE TABLE system_metadata (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Insert initial metadata
INSERT INTO system_metadata (key, value) VALUES
    ('schema_version', '1.0.0'),
    ('last_event_export', ''),
    ('last_market_filter', ''),
    ('last_signal_generation', ''),
    ('last_trade_execution', '');
```

---

## Database Connection Configuration

### Environment Variables (`.env`)
```bash
# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=prescient_os
POSTGRES_USER=prescient_user
POSTGRES_PASSWORD=your_secure_password

# Migration Configuration
USE_DATABASE_WRITE=true
USE_DATABASE_READ=false  # Start with false, flip to true in Phase 5
DATABASE_FALLBACK_TO_JSON=true  # Keep true until Phase 7
```

### Connection Manager (`src/db/connection.py`)
```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Database URL
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=os.getenv('SQL_DEBUG', 'false').lower() == 'true'
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    """Database session context manager"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()

def test_connection():
    """Test database connectivity"""
    try:
        with get_db() as db:
            db.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
```

---

## Migration Helpers

### Dual-Write Helper (`src/db/dual_write.py`)
```python
import json
import os
from typing import Any, Callable
import logging

logger = logging.getLogger(__name__)

USE_DATABASE_WRITE = os.getenv('USE_DATABASE_WRITE', 'false').lower() == 'true'
USE_DATABASE_READ = os.getenv('USE_DATABASE_READ', 'false').lower() == 'true'

def dual_write(json_func: Callable, db_func: Callable, *args, **kwargs) -> Any:
    """
    Execute both JSON and database writes during migration phase

    Args:
        json_func: Function to write to JSON
        db_func: Function to write to database
        *args, **kwargs: Arguments for both functions

    Returns:
        Result from JSON function (primary during migration)
    """
    # Always write to JSON (primary during phases 1-5)
    json_result = json_func(*args, **kwargs)

    # Attempt database write if enabled
    if USE_DATABASE_WRITE:
        try:
            db_func(*args, **kwargs)
            logger.debug("Successfully wrote to database")
        except Exception as e:
            logger.error(f"Database write failed (non-fatal): {e}")
            # Don't raise - JSON is still source of truth

    return json_result

def dual_read(json_func: Callable, db_func: Callable, *args, **kwargs) -> Any:
    """
    Read from database or JSON based on configuration

    Args:
        json_func: Function to read from JSON
        db_func: Function to read from database
        *args, **kwargs: Arguments for both functions

    Returns:
        Data from configured source
    """
    if USE_DATABASE_READ:
        try:
            return db_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Database read failed, falling back to JSON: {e}")
            return json_func(*args, **kwargs)
    else:
        return json_func(*args, **kwargs)
```

---

## Testing Strategy

### Phase-by-Phase Testing

1. **Phase 0**: Database connection test
   ```bash
   python -c "from src.db.connection import test_connection; print(test_connection())"
   ```

2. **Phases 1-4**: Data consistency tests
   ```python
   # scripts/test_data_consistency.py
   # Compare JSON vs PostgreSQL data
   # Verify all writes appear in both locations
   ```

3. **Phase 5**: Read performance tests
   ```python
   # scripts/benchmark_reads.py
   # Compare JSON vs PostgreSQL read performance
   ```

4. **Phase 6-7**: System stability tests
   - Run full trading cycle 100 times
   - Verify zero data loss
   - Test failure scenarios (database down, network issues)

---

## Rollback Plan

### Each Phase Has Rollback:
1. **Phases 1-4**: Simply disable `USE_DATABASE_WRITE` environment variable
2. **Phase 5**: Set `USE_DATABASE_READ=false` to revert to JSON reads
3. **Phase 6-7**: Emergency restore from JSON backup files

### Backup Strategy:
- Daily PostgreSQL backups: `pg_dump prescient_os > backup_$(date +%Y%m%d).sql`
- Keep JSON files for 30 days after Phase 7 completion
- Weekly full backup to external storage

---

## Benefits After Migration

### Performance:
-  Faster queries with indexes (especially for analytics)
-  Join operations for complex queries (trades + markets + events)
-  Time-series analysis on market/portfolio data

### Features Enabled:
-  Real-time P&L tracking with market price updates
-  Advanced analytics (win rate, best markets, strategy performance)
-  Historical backtesting against real market data
-  Multi-strategy comparison
-  Trade correlation analysis

### Reliability:
-  ACID transactions (no partial writes)
-  Referential integrity (signals ’ trades ’ portfolio)
-  Concurrent access support (future multi-user)
-  Professional backup/restore procedures

### Scalability:
-  Handles millions of trades without performance degradation
-  Efficient storage (no duplicate market data)
-  Query optimization with indexes
-  Prepared for real-money trading scale

---

## Timeline Summary

| Phase | Duration | Risk Level | Effort |
|-------|----------|-----------|--------|
| Phase 0: Preparation | 1 week | Low | Medium |
| Phase 1: Trades & Portfolio | 1 week | Low | Low |
| Phase 2: Historical Data | 1 week | Low | Low |
| Phase 3: Trading Signals | 1 week | Low | Medium |
| Phase 4: Markets & Events | 1 week | Medium | Medium |
| Phase 5: Switch to DB Reads | 1 week | Medium | Medium |
| Phase 6: Remove JSON Writes | 1 week | Medium | Low |
| Phase 7: Deprecate JSON | 1 week | Low | Low |
| **Total** | **8 weeks** | | |

---

## Success Metrics

### After Phase 1:
- [ ] 100% of trades written to both JSON and PostgreSQL
- [ ] Zero data inconsistencies

### After Phase 4:
- [ ] All data flows to PostgreSQL
- [ ] System stable with dual-write for 1 week

### After Phase 5:
- [ ] All reads from PostgreSQL
- [ ] Read performance e JSON baseline
- [ ] Zero failed reads

### After Phase 7:
- [ ] No JSON dependencies in code
- [ ] Database backup/restore tested
- [ ] Monitoring dashboards operational
- [ ] Team trained on PostgreSQL operations

---

## Next Steps

1. **Review this plan** with the team
2. **Set up development database** (Phase 0)
3. **Create database models and schema** (Phase 0)
4. **Begin Phase 1** implementation with trades & portfolio
5. **Monitor and iterate** based on learnings

---

## Notes & Considerations

### Why This Approach Works:
-  **Low risk**: JSON remains source of truth until Phase 6
-  **Incremental**: Each phase adds value independently
-  **Reversible**: Easy rollback at any stage
-  **Testable**: Can validate at each step
-  **Business continuity**: Trading never stops

### Alternative Approaches Considered:
- L **Big-bang migration**: Too risky, all-or-nothing
- L **Database-first**: Breaks system if database fails
- L **Dual-primary**: Complex conflict resolution

### Critical Success Factors:
1. **Always prioritize data integrity** over speed
2. **Monitor database performance** from day one
3. **Keep JSON fallback** until 100% confident
4. **Test failure scenarios** at each phase
5. **Document all schema changes** with Alembic

---

*Last Updated: 2025-10-27*
*Version: 1.0*
