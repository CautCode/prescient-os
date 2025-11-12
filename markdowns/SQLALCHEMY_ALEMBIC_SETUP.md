# SQLAlchemy + Alembic Setup Guide

This guide explains how to set up SQLAlchemy ORM and Alembic migrations for Prescient OS after completing the manual database migration.

---

## Why Use SQLAlchemy + Alembic?

### Advantages over raw SQL:

1. **Better Code Quality**: SQLAlchemy models are cleaner and more maintainable than raw SQL strings
2. **Type Safety**: IDE autocomplete, type checking, and fewer runtime errors
3. **No SQL Injection**: Automatic parameterization and escaping
4. **Relationships**: Automatic handling of foreign keys and joins (`portfolio.positions` instead of manual joins)
5. **Database Agnostic**: Easy to switch databases if needed
6. **Version Control**: Alembic tracks schema changes with git-friendly migration files
7. **Rollback Support**: Easy to revert migrations if issues occur
8. **Team Collaboration**: Everyone runs the same migrations in the same order

### When to use this approach:
- **After** you've completed the manual database migration
- You want to use SQLAlchemy ORM for cleaner database operations
- You want version-controlled migrations for future schema changes

---

## Timeline

This should be done **after** the manual migration is complete:

```
Week 1-2: Manual migration → Multi-portfolio DB schema ✓
Week 2-3: Update controllers to use new schema (raw SQL) ✓
Week 3:   Install Alembic, create models, baseline migration ← THIS GUIDE
Week 4-5: Gradually rewrite operations.py to use SQLAlchemy ✓
Week 6+:  Use Alembic for all future migrations ✓
```

---

## Step 1: Install Dependencies

```bash
pip install alembic sqlalchemy psycopg2-binary
```

Add to `requirements.txt`:
```
alembic==1.13.1
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
```

---

## Step 2: Create SQLAlchemy Models

Create `src/db/models.py` with all table models:

```python
# src/db/models.py

"""
SQLAlchemy ORM models for Prescient OS database

These models replace raw SQL operations and enable:
- Type-safe database operations
- Automatic relationship handling
- Better IDE support
- Cleaner, more maintainable code
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, DECIMAL, TIMESTAMP, Boolean,
    ForeignKey, Index, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


# ============================================================================
# PORTFOLIO MODELS
# ============================================================================

class Portfolio(Base):
    """
    Portfolio model - central table for multi-portfolio system

    Replaces the old portfolio_state table with support for multiple
    independent portfolios with different strategies
    """
    __tablename__ = 'portfolios'

    # Primary Key
    portfolio_id = Column(Integer, primary_key=True, autoincrement=True)

    # Identity
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    strategy_type = Column(String(100), nullable=False)

    # Financial State
    initial_balance = Column(DECIMAL(15, 2), nullable=False)
    current_balance = Column(DECIMAL(15, 2), nullable=False)
    total_invested = Column(DECIMAL(15, 2), default=0)
    total_profit_loss = Column(DECIMAL(15, 2), default=0)
    trade_count = Column(Integer, default=0)

    # Status
    status = Column(String(50), default='active')
    created_at = Column(TIMESTAMP, default=func.now())
    last_updated = Column(TIMESTAMP, default=func.now(), onupdate=func.now())

    # Strategy Configuration (flexible JSONB)
    strategy_config = Column(JSONB, default={})

    # Risk Management
    max_position_size = Column(DECIMAL(15, 2))
    max_total_exposure = Column(DECIMAL(15, 2))
    max_positions = Column(Integer, default=20)

    # Performance Tracking
    total_trades_executed = Column(Integer, default=0)
    total_winning_trades = Column(Integer, default=0)
    total_losing_trades = Column(Integer, default=0)
    avg_trade_pnl = Column(DECIMAL(15, 2), default=0)
    max_drawdown = Column(DECIMAL(15, 2), default=0)

    # Metadata
    last_trade_at = Column(TIMESTAMP)
    last_price_update = Column(TIMESTAMP)

    # Relationships
    positions = relationship("PortfolioPosition", back_populates="portfolio", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="portfolio", cascade="all, delete-orphan")
    signals = relationship("TradingSignal", back_populates="portfolio", cascade="all, delete-orphan")
    history = relationship("PortfolioHistory", back_populates="portfolio", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index('idx_portfolios_status', 'status'),
        Index('idx_portfolios_strategy_type', 'strategy_type'),
        Index('idx_portfolios_status_strategy', 'status', 'strategy_type'),
    )

    def __repr__(self):
        return f"<Portfolio(id={self.portfolio_id}, name='{self.name}', strategy='{self.strategy_type}', balance=${self.current_balance})>"


class PortfolioPosition(Base):
    """
    Portfolio positions - tracks open and closed positions per portfolio
    """
    __tablename__ = 'portfolio_positions'

    # Note: Existing table, we're adding portfolio_id column
    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.portfolio_id', ondelete='CASCADE'), nullable=False)

    trade_id = Column(String(255))
    market_id = Column(String(255))
    market_question = Column(Text)
    action = Column(String(50))
    amount = Column(DECIMAL(15, 2))
    entry_price = Column(DECIMAL(10, 6))
    entry_timestamp = Column(TIMESTAMP)
    status = Column(String(50))
    current_pnl = Column(DECIMAL(15, 2))
    realized_pnl = Column(DECIMAL(15, 2))
    exit_price = Column(DECIMAL(10, 6))
    exit_timestamp = Column(TIMESTAMP)

    # Relationships
    portfolio = relationship("Portfolio", back_populates="positions")

    # Indexes
    __table_args__ = (
        Index('idx_portfolio_positions_portfolio_id', 'portfolio_id'),
        Index('idx_portfolio_positions_portfolio_status', 'portfolio_id', 'status'),
        Index('idx_portfolio_positions_portfolio_market', 'portfolio_id', 'market_id'),
    )

    def __repr__(self):
        return f"<Position(portfolio={self.portfolio_id}, market={self.market_id}, status={self.status}, pnl=${self.current_pnl})>"


class Trade(Base):
    """
    Trades table - all executed trades per portfolio
    """
    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.portfolio_id', ondelete='CASCADE'), nullable=False)

    trade_id = Column(String(255))
    timestamp = Column(TIMESTAMP)
    market_id = Column(String(255))
    market_question = Column(Text)
    action = Column(String(50))
    amount = Column(DECIMAL(15, 2))
    entry_price = Column(DECIMAL(10, 6))
    confidence = Column(DECIMAL(5, 4))
    reason = Column(Text)
    status = Column(String(50))
    event_id = Column(String(255))
    event_title = Column(Text)
    event_end_date = Column(TIMESTAMP)
    current_pnl = Column(DECIMAL(15, 2))
    realized_pnl = Column(DECIMAL(15, 2))

    # Relationships
    portfolio = relationship("Portfolio", back_populates="trades")

    # Indexes
    __table_args__ = (
        Index('idx_trades_portfolio_id', 'portfolio_id'),
        Index('idx_trades_portfolio_timestamp', 'portfolio_id', 'timestamp'),
        Index('idx_trades_portfolio_status', 'portfolio_id', 'status'),
    )

    def __repr__(self):
        return f"<Trade(id={self.trade_id}, portfolio={self.portfolio_id}, market={self.market_id}, amount=${self.amount})>"


class TradingSignal(Base):
    """
    Trading signals - generated by strategy controllers
    """
    __tablename__ = 'trading_signals'

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.portfolio_id', ondelete='CASCADE'))
    strategy_type = Column(String(100))

    timestamp = Column(TIMESTAMP)
    market_id = Column(String(255))
    market_question = Column(Text)
    action = Column(String(50))
    target_price = Column(DECIMAL(10, 6))
    amount = Column(DECIMAL(15, 2))
    confidence = Column(DECIMAL(5, 4))
    reason = Column(Text)
    yes_price = Column(DECIMAL(10, 6))
    no_price = Column(DECIMAL(10, 6))
    market_liquidity = Column(DECIMAL(15, 2))
    market_volume = Column(DECIMAL(15, 2))
    event_id = Column(String(255))
    event_title = Column(Text)
    event_end_date = Column(TIMESTAMP)
    executed = Column(Boolean, default=False)
    executed_at = Column(TIMESTAMP)
    trade_id = Column(String(255))

    # Relationships
    portfolio = relationship("Portfolio", back_populates="signals")

    # Indexes
    __table_args__ = (
        Index('idx_trading_signals_portfolio', 'portfolio_id'),
        Index('idx_trading_signals_portfolio_executed', 'portfolio_id', 'executed'),
        Index('idx_trading_signals_strategy', 'strategy_type'),
    )

    def __repr__(self):
        return f"<Signal(id={self.id}, portfolio={self.portfolio_id}, market={self.market_id}, executed={self.executed})>"


class PortfolioHistory(Base):
    """
    Portfolio history snapshots - daily tracking of portfolio state
    """
    __tablename__ = 'portfolio_history'

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.portfolio_id', ondelete='CASCADE'), nullable=False)

    snapshot_date = Column(TIMESTAMP)
    timestamp = Column(TIMESTAMP)
    balance = Column(DECIMAL(15, 2))
    total_invested = Column(DECIMAL(15, 2))
    total_profit_loss = Column(DECIMAL(15, 2))
    total_value = Column(DECIMAL(15, 2))
    open_positions = Column(Integer)
    trade_count = Column(Integer)

    # Relationships
    portfolio = relationship("Portfolio", back_populates="history")

    # Indexes
    __table_args__ = (
        Index('idx_portfolio_history_portfolio_date', 'portfolio_id', 'snapshot_date'),
        Index('idx_portfolio_history_portfolio_timestamp', 'portfolio_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<PortfolioHistory(portfolio={self.portfolio_id}, date={self.snapshot_date}, value=${self.total_value})>"


# ============================================================================
# EVENTS & MARKETS MODELS (for completeness)
# ============================================================================

class Event(Base):
    """Events from Polymarket"""
    __tablename__ = 'events'

    event_id = Column(String(255), primary_key=True)
    title = Column(Text)
    slug = Column(String(255))
    description = Column(Text)
    start_date = Column(TIMESTAMP)
    end_date = Column(TIMESTAMP)
    image_url = Column(Text)
    icon = Column(String(255))
    active = Column(Boolean)
    closed = Column(Boolean)
    archived = Column(Boolean)
    new = Column(Boolean)
    featured = Column(Boolean)
    restricted = Column(Boolean)
    liquidity = Column(DECIMAL(15, 2))
    volume = Column(DECIMAL(15, 2))
    tags = Column(JSONB)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP)
    is_filtered = Column(Boolean, default=False)

    def __repr__(self):
        return f"<Event(id={self.event_id}, title='{self.title}')>"


class Market(Base):
    """Markets from Polymarket"""
    __tablename__ = 'markets'

    market_id = Column(String(255), primary_key=True)
    event_id = Column(String(255))
    question = Column(Text)
    description = Column(Text)
    outcomes = Column(JSONB)
    outcome_prices = Column(JSONB)
    volume = Column(DECIMAL(15, 2))
    volume24hr = Column(DECIMAL(15, 2))
    liquidity = Column(DECIMAL(15, 2))
    end_date = Column(TIMESTAMP)
    game_start_time = Column(TIMESTAMP)
    seconds_delay = Column(Integer)
    active = Column(Boolean)
    closed = Column(Boolean)
    archived = Column(Boolean)
    new = Column(Boolean)
    featured = Column(Boolean)
    submitted_by = Column(String(255))
    resolved = Column(Boolean)
    yes_price = Column(DECIMAL(10, 6))
    no_price = Column(DECIMAL(10, 6))
    last_price_update = Column(TIMESTAMP)
    market_conviction = Column(DECIMAL(5, 4))
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP)
    is_filtered = Column(Boolean, default=False)

    def __repr__(self):
        return f"<Market(id={self.market_id}, question='{self.question}')>"


class MarketSnapshot(Base):
    """Historical snapshots of market prices"""
    __tablename__ = 'market_snapshots'

    id = Column(Integer, primary_key=True)
    market_id = Column(String(255))
    timestamp = Column(TIMESTAMP, default=func.now())
    yes_price = Column(DECIMAL(10, 6))
    no_price = Column(DECIMAL(10, 6))
    liquidity = Column(DECIMAL(15, 2))
    volume = Column(DECIMAL(15, 2))
    volume24hr = Column(DECIMAL(15, 2))
    market_conviction = Column(DECIMAL(5, 4))

    __table_args__ = (
        Index('idx_market_snapshots_market_timestamp', 'market_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<MarketSnapshot(market={self.market_id}, timestamp={self.timestamp})>"
```

---

## Step 3: Update Database Connection

Add a `get_database_url()` function to your `src/db/connection.py`:

```python
# src/db/connection.py

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

load_dotenv()


def get_database_url() -> str:
    """Get database URL for Alembic and SQLAlchemy"""
    return (
        f"postgresql://{os.getenv('POSTGRES_USER')}:"
        f"{os.getenv('POSTGRES_PASSWORD')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB')}"
    )


# Create SQLAlchemy engine
engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Session:
    """
    Context manager for SQLAlchemy sessions

    Usage:
        with get_db_session() as session:
            portfolio = session.query(Portfolio).filter_by(portfolio_id=1).first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

---

## Step 4: Initialize Alembic

```bash
# Initialize Alembic in your project root
alembic init alembic
```

This creates:
```
alembic/
  ├── versions/          # Migration files go here
  ├── env.py            # Alembic environment configuration
  ├── script.py.mako    # Template for new migrations
  └── README
alembic.ini             # Alembic configuration file
```

---

## Step 5: Configure Alembic

Edit `alembic/env.py` to connect to your database and use your models:

```python
# alembic/env.py

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Add your project to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import your models
from src.db.models import Base
from src.db.connection import get_database_url

# this is the Alembic Config object
config = context.config

# Set the database URL from your environment
config.set_main_option('sqlalchemy.url', get_database_url())

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## Step 6: Create Baseline Migration

Since your database is already migrated with the manual script, you need to create a "baseline" migration that represents the current state:

```bash
# Generate a migration that shows current database state
alembic revision --autogenerate -m "Baseline after manual migration"
```

This will create a file like `alembic/versions/xxxx_baseline_after_manual_migration.py`

**IMPORTANT**: Review this file! It should detect the existing tables (portfolios, etc.) and generate the migration.

---

## Step 7: Mark as Applied (Don't Run It!)

Since the database is already in this state, you need to tell Alembic "the database is already at this version":

```bash
# Mark the migration as applied without actually running it
alembic stamp head
```

This tells Alembic: "The database is at this state, don't try to run this migration again."

---

## Step 8: Verify Alembic Setup

```bash
# Check current migration version
alembic current

# Should show your baseline migration

# Check history
alembic history
```

---

## Step 9: Gradually Rewrite Operations

Now you can start rewriting `src/db/operations.py` functions to use SQLAlchemy. Do this **gradually**, one function at a time.

### Example: Before (Raw SQL)

```python
def get_portfolio_state(portfolio_id: int = None) -> Dict:
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
            # ... manual mapping of 15+ fields
        }
```

### Example: After (SQLAlchemy)

```python
def get_portfolio_state(portfolio_id: int = None) -> Dict:
    with get_db_session() as session:
        if portfolio_id is None:
            # Get first active portfolio
            portfolio = session.query(Portfolio).filter_by(status='active').first()
        else:
            portfolio = session.query(Portfolio).filter_by(portfolio_id=portfolio_id).first()

        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        # Clean attribute access instead of index mapping!
        return {
            'portfolio_id': portfolio.portfolio_id,
            'name': portfolio.name,
            'description': portfolio.description,
            'strategy_type': portfolio.strategy_type,
            'initial_balance': float(portfolio.initial_balance),
            'current_balance': float(portfolio.current_balance),
            'total_invested': float(portfolio.total_invested),
            'total_profit_loss': float(portfolio.total_profit_loss),
            'trade_count': portfolio.trade_count,
            'status': portfolio.status,
            'created_at': portfolio.created_at,
            'last_updated': portfolio.last_updated,
            'strategy_config': portfolio.strategy_config,
            'max_position_size': float(portfolio.max_position_size) if portfolio.max_position_size else None,
            'max_total_exposure': float(portfolio.max_total_exposure) if portfolio.max_total_exposure else None,
            'max_positions': portfolio.max_positions
        }
```

### Example: Using Relationships (No Manual Joins!)

```python
def get_portfolio_positions(portfolio_id: int, status: str = 'open') -> List[Dict]:
    """Get positions using relationship - no manual joins needed!"""
    with get_db_session() as session:
        portfolio = session.query(Portfolio).filter_by(portfolio_id=portfolio_id).first()

        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        # Use the relationship! SQLAlchemy handles the join automatically
        positions = [p for p in portfolio.positions if p.status == status]

        return [
            {
                'trade_id': pos.trade_id,
                'market_id': pos.market_id,
                'market_question': pos.market_question,
                'action': pos.action,
                'amount': float(pos.amount),
                'entry_price': float(pos.entry_price),
                'entry_timestamp': pos.entry_timestamp.isoformat() if pos.entry_timestamp else None,
                'status': pos.status,
                'current_pnl': float(pos.current_pnl) if pos.current_pnl else 0.0,
                'realized_pnl': float(pos.realized_pnl) if pos.realized_pnl else None,
                'exit_price': float(pos.exit_price) if pos.exit_price else None,
                'exit_timestamp': pos.exit_timestamp.isoformat() if pos.exit_timestamp else None
            }
            for pos in positions
        ]
```

**Test each function after rewriting it!**

---

## Step 10: Future Schema Changes with Alembic

Now that Alembic is set up, you can use it for all future migrations:

### Example: Adding a New Column

1. **Update your SQLAlchemy model**:
   ```python
   # In src/db/models.py
   class Portfolio(Base):
       # ... existing fields ...
       performance_score = Column(DECIMAL(5, 2))  # NEW FIELD
   ```

2. **Generate migration**:
   ```bash
   alembic revision --autogenerate -m "Add performance_score to portfolios"
   ```

3. **Review the migration**:
   Alembic creates `alembic/versions/xxxx_add_performance_score_to_portfolios.py`

   Review it to make sure it looks correct!

4. **Run the migration**:
   ```bash
   alembic upgrade head
   ```

5. **Rollback if needed**:
   ```bash
   alembic downgrade -1
   ```

---

## Alembic Cheat Sheet

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head          # Upgrade to latest
alembic upgrade +1            # Upgrade one version
alembic upgrade <revision>    # Upgrade to specific revision

# Rollback migrations
alembic downgrade -1          # Rollback one version
alembic downgrade <revision>  # Rollback to specific revision
alembic downgrade base        # Rollback all migrations

# View history
alembic current              # Show current version
alembic history              # Show all migrations
alembic show <revision>      # Show specific migration

# Generate SQL without running
alembic upgrade head --sql   # Preview SQL
```

---

## Code Quality Comparison

### Raw SQL (Before):
```python
# Lots of manual work
result = db.execute(text("""
    SELECT p.*, COUNT(pp.id) as position_count
    FROM portfolios p
    LEFT JOIN portfolio_positions pp ON p.portfolio_id = pp.portfolio_id
    WHERE p.portfolio_id = :portfolio_id
    GROUP BY p.portfolio_id
"""), {'portfolio_id': portfolio_id}).fetchone()

# Manual index-based mapping
return {
    'portfolio_id': result[0],
    'name': result[1],
    # ... 20 more lines of index mapping
}
```

### SQLAlchemy (After):
```python
# Clean and readable
portfolio = session.query(Portfolio).filter_by(portfolio_id=portfolio_id).first()

# Use relationships automatically
position_count = len(portfolio.positions)

# Clean attribute access
return {
    'portfolio_id': portfolio.portfolio_id,
    'name': portfolio.name,
    'position_count': position_count
}
```

**Much cleaner!**

---

## Summary

1. **Install** SQLAlchemy and Alembic
2. **Create** `src/db/models.py` with ORM models matching your new schema
3. **Update** `src/db/connection.py` with `get_database_url()` and session management
4. **Initialize** Alembic with `alembic init alembic`
5. **Configure** `alembic/env.py` to use your models
6. **Generate** baseline migration with `alembic revision --autogenerate`
7. **Mark as applied** with `alembic stamp head` (don't run the migration!)
8. **Gradually rewrite** operations.py functions to use SQLAlchemy
9. **Use Alembic** for all future schema changes

This gives you the best of both worlds:
- Fast migration with the manual script
- Clean, maintainable code with SQLAlchemy
- Version-controlled schema changes with Alembic

---

*This should be implemented in Weeks 3-5 after the manual migration is complete.*