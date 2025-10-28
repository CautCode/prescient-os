# Prescient OS Database Tables Reference

This document explains the purpose and structure of each table in the Prescient OS PostgreSQL database.

---

## 📊 Portfolio Management Tables

### `portfolio_state`
**Purpose**: Stores the current overall portfolio state (single record, updated frequently)
- **Key Fields**: balance, total_invested, total_profit_loss, trade_count
- **Usage**: Real-time portfolio balance and P&L tracking
- **Updates**: Modified by price updater every 5 minutes, trade executions
- **Constraints**: Only one row (id = 1)

### `portfolio_positions`
**Purpose**: Tracks individual open trading positions
- **Key Fields**: trade_id, market_id, action, amount, entry_price, current_pnl, status
- **Usage**: Monitor active trades, calculate unrealized P&L
- **Updates**: Created when trades execute, updated by price updater
- **Indexes**: market_id, status for fast queries

### `portfolio_history`
**Purpose**: Daily snapshots of portfolio state for historical analysis
- **Key Fields**: snapshot_date, balance, total_invested, total_profit_loss, total_value
- **Usage**: Track portfolio performance over time, generate reports
- **Updates**: Created daily by trading controller
- **Indexes**: snapshot_date for time-based queries

### `portfolio_snapshots`
**Purpose**: Timestamped portfolio states (more frequent than daily history)
- **Key Fields**: timestamp, balance, total_invested, total_profit_loss, trade_count
- **Usage**: Detailed portfolio tracking, debugging, analytics
- **Updates**: Created on significant portfolio changes

---

## 💼 Trade Management Tables

### `trades`
**Purpose**: Complete history of all executed trades (append-only)
- **Key Fields**: trade_id, timestamp, market_id, action, amount, entry_price, confidence, status
- **Usage**: Trade history, performance analysis, backtesting
- **Updates**: Inserted when trades execute, status updated on closure
- **Indexes**: market_id, timestamp, status for analytics queries
- **Relationships**: Referenced by trading_signals (trade_id)

### `trading_signals`
**Purpose**: Current and historical trading signals with execution tracking
- **Key Fields**: market_id, action, target_price, confidence, executed, trade_id
- **Usage**: Signal generation, execution tracking, strategy analysis
- **Updates**: Created by strategy controller, marked executed by trading controller
- **Indexes**: market_id, timestamp, executed for signal management
- **Relationships**: Links to trades via trade_id foreign key

### `signal_archives`
**Purpose**: Monthly archives of trading signals for long-term storage
- **Key Fields**: archive_month, signals_count, signals_data (JSONB)
- **Usage**: Historical signal analysis, strategy performance over time
- **Updates**: Created monthly by trading controller
- **Indexes**: archive_month for archive retrieval

---

## 🏛️ Market Data Tables

### `markets`
**Purpose**: Filtered markets with current pricing and metadata
- **Key Fields**: market_id, question, yes_price, no_price, liquidity, volume
- **Usage**: Current market data for trading decisions, price monitoring
- **Updates**: Updated by market controller, price updater
- **Indexes**: market_id, event_id, liquidity, volume for filtering
- **Storage**: Full market JSON stored in market_data (JSONB)

### `market_snapshots`
**Purpose**: Time-series price history for all markets
- **Key Fields**: market_id, timestamp, yes_price, no_price, liquidity, volume
- **Usage**: Price history analysis, market trend tracking, backtesting
- **Updates**: Created by price updater every 5 minutes for active markets
- **Indexes**: market_id, timestamp for time-series queries

### `events`
**Purpose**: Filtered events containing multiple markets
- **Key Fields**: event_id, title, liquidity, volume, start_date, end_date
- **Usage**: Event-level filtering, market discovery, event analysis
- **Updates**: Updated by events controller
- **Indexes**: event_id, liquidity, volume, end_date for filtering
- **Storage**: Full event JSON stored in event_data (JSONB)

---

## ⚙️ System Tables

### `system_metadata`
**Purpose**: System configuration and status tracking
- **Key Fields**: key, value (key-value pairs)
- **Usage**: Track system state, migration status, last update timestamps
- **Examples**:
  - `schema_version`: Database schema version
  - `last_event_export`: Timestamp of last event data refresh
  - `last_market_filter`: Timestamp of last market filtering
  - `last_signal_generation`: Timestamp of last signal generation
  - `last_trade_execution`: Timestamp of last trade execution

---

## 🔗 Table Relationships

```
trading_signals (trade_id) ────► trades (trade_id)
markets (event_id) ─────────────► events (event_id)
market_snapshots (market_id) ──► markets (market_id)
portfolio_positions (trade_id) ─► trades (trade_id)
```

---

## 📈 Data Flow

1. **Events Controller** → `events` table
2. **Market Controller** → `markets` table
3. **Strategy Controller** → `trading_signals` table
4. **Paper Trading Controller** → `trades`, `portfolio_positions`, `portfolio_state` tables
5. **Price Updater** → Updates `portfolio_positions`, `portfolio_state`, creates `market_snapshots`
6. **Trading Controller** → Creates `portfolio_history`, `signal_archives`

---

## 🔍 Common Query Patterns

### Portfolio Analysis
```sql
-- Current portfolio value
SELECT balance + total_profit_loss as total_value FROM portfolio_state WHERE id = 1;

-- Open positions with P&L
SELECT market_id, action, amount, entry_price, current_pnl
FROM portfolio_positions
WHERE status = 'open'
ORDER BY current_pnl DESC;
```

### Trade Performance
```sql
-- Recent trades
SELECT timestamp, market_id, action, amount, entry_price, realized_pnl
FROM trades
WHERE status = 'closed'
ORDER BY timestamp DESC
LIMIT 10;

-- Win rate analysis
SELECT
    COUNT(*) as total_trades,
    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
    AVG(realized_pnl) as avg_pnl
FROM trades
WHERE status = 'closed';
```

### Market Analysis
```sql
-- Active markets by volume
SELECT market_id, question, volume, yes_price, no_price
FROM markets
WHERE is_filtered = true
ORDER BY volume DESC
LIMIT 20;

-- Price history for specific market
SELECT timestamp, yes_price, no_price, volume
FROM market_snapshots
WHERE market_id = 'specific_market_id'
ORDER BY timestamp DESC
LIMIT 100;
```

### Signal Analysis
```sql
-- Current signals
SELECT market_id, action, confidence, target_price, executed
FROM trading_signals
WHERE executed = false
ORDER BY confidence DESC;

-- Signal to trade conversion rate
SELECT
    COUNT(*) as total_signals,
    SUM(CASE WHEN executed = true THEN 1 ELSE 0 END) as executed_signals
FROM trading_signals
WHERE timestamp > NOW() - INTERVAL '30 days';
```

---

## 📊 Table Sizes & Growth

| Table | Growth Rate | Retention | Purpose |
|-------|-------------|-----------|---------|
| `trades` | High (every trade) | Permanent | Audit trail |
| `market_snapshots` | High (every 5 min × active markets) | 90 days | Price history |
| `portfolio_history` | Daily | Permanent | Portfolio tracking |
| `trading_signals` | Medium (per signal generation) | 30 days | Signal tracking |
| `signal_archives` | Monthly | Permanent | Long-term signals |
| `markets`/`events` | Medium (updates) | 30 days | Current data |
| `portfolio_state` | Frequent updates | Current only | Live state |
| `portfolio_positions` | Medium (open positions) | Until closed | Active trades |

---

## 🔧 Maintenance Tasks

### Daily
- Price updater creates `market_snapshots` for active markets
- Trading controller creates `portfolio_history` snapshot

### Weekly
- Archive old `market_snapshots` (>90 days)
- Clean up old `trading_signals` (>30 days)

### Monthly
- Create `signal_archives` from old signals
- Review and archive old market/event data

---

## 🚨 Critical Tables (System Down if Missing)

1. **`portfolio_state`** - Current balance and P&L
2. **`portfolio_positions`** - Active trades
3. **`trades`** - Trade history and audit trail
4. **`trading_signals`** - Current trading signals

---

## 📈 Analytics Tables (Performance Monitoring)

1. **`market_snapshots`** - Price movement analysis
2. **`portfolio_history`** - Portfolio performance over time
3. **`trades`** - Trade performance and win rates
4. **`signal_archives`** - Strategy effectiveness over time

---

*Last Updated: 2025-10-28*
*Database Version: 1.0*