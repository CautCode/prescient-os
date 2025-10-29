# Prescient OS Code Flow Documentation

This document explains the step-by-step flow of how the Prescient OS trading system works, including the order of controller usage and price updates.

---

## 🔄 System Overview

The Prescient OS is an automated trading system for Polymarket that follows a structured pipeline:
1. **Data Collection** → **Filtering** → **Signal Generation** → **Trade Execution** → **Portfolio Management**
2. **Continuous Price Updates** run in parallel to keep portfolio P&L accurate

---

## 📋 Controller Order and Responsibilities

### 1. Events Controller (Port 8000)
**Purpose**: Fetches and filters events from Polymarket API
**When Used**: First step in trading cycle
**Key Functions**:
- Export all active events from Polymarket
- Filter events based on liquidity, volume, and time criteria
- Store filtered events in `events` table

### 2. Market Controller (Port 8001)
**Purpose**: Fetches and filters individual markets within events
**When Used**: Second step after event filtering
**Key Functions**:
- Export detailed market data for filtered events
- Filter markets based on liquidity, volume, and conviction thresholds
- Store filtered markets in `markets` table

### 3. Trading Strategy Controller (Port 8002)
**Purpose**: Analyzes markets and generates trading signals
**When Used**: Third step after market filtering
**Key Functions**:
- Analyzes filtered markets for trading opportunities
- Generates buy/sell signals with confidence scores
- Stores signals in `trading_signals` table

### 4. Paper Trading Controller (Port 8003)
**Purpose**: Executes virtual trades and manages portfolio
**When Used**: Fourth step for signal execution
**Key Functions**:
- Executes trading signals with virtual money
- Manages portfolio state and positions
- Tracks trade history and P&L
- **Starts and manages the Price Updater**

### 5. Trading Controller (Port 8004)
**Purpose**: Orchestrates the complete trading cycle
**When Used**: Main entry point that coordinates all controllers
**Key Functions**:
- Calls all other controllers in sequence
- Creates portfolio snapshots and archives
- Provides system status and performance summaries

---

## 🔄 Complete Trading Cycle Flow

### Step 1: Event Data Collection
```
Events Controller → /events/export-all-active-events-db
├── Fetches all active events from Polymarket API
├── Stores raw event data in database
└── Returns count of exported events
```

### Step 2: Event Filtering
```
Events Controller → /events/filter-trading-candidates-db
├── Applies liquidity/volume/time filters
├── Stores filtered events in `events` table
└── Returns trading candidate count
```

### Step 3: Market Data Collection
```
Market Controller → /markets/export-filtered-markets-db
├── Fetches detailed market data for filtered events
├── Applies market-specific filters
└── Stores filtered markets in `markets` table
```

### Step 4: Signal Generation
```
Strategy Controller → /strategy/generate-signals
├── Analyzes filtered markets
├── Generates trading signals with confidence scores
└── Stores signals in `trading_signals` table
```

### Step 5: Trade Execution
```
Paper Trading Controller → /paper-trading/execute-signals
├── Loads unexecuted signals from database
├── Executes trades with virtual money
├── Updates portfolio state
├── Records trades in `trades` table
├── Creates positions in `portfolio_positions` table
└── Marks signals as executed
```

### Step 6: Portfolio Snapshot
```
Paper Trading Controller → /paper-trading/portfolio
├── Loads current portfolio state
├── Updates P&L with current market prices
└── Trading Controller creates daily snapshot in `portfolio_history` table
```

### Step 7: Signal Archiving
```
Trading Controller → archive_current_signals()
├── Archives executed signals to `signal_archives` table
└── Cleans up old signals from `trading_signals` table
```

---

## 💰 Price Update Flow (Continuous Background Process)

### Price Updater Initialization
```
Paper Trading Controller Startup
├── Starts Price Updater background thread
├── Sets update interval (default: 5 minutes)
└── Begins continuous price monitoring
```

### Price Update Cycle (Every 5 Minutes)
```
Price Updater → update_open_positions_prices()
├── Step 1: Load open positions from `portfolio_positions` table
├── Step 2: Extract unique market IDs from positions
├── Step 3: Fetch current prices from Polymarket API (batched requests)
├── Step 4: Calculate P&L for each position:
│   ├── Get current price based on action (buy_yes/buy_no)
│   ├── Calculate: P&L = (current_price - entry_price) × amount
│   ├── Update position in `portfolio_positions` table
│   └── Accumulate total P&L
├── Step 5: Update portfolio state:
│   ├── Update `total_profit_loss` in `portfolio_state` table
│   └── Update `last_updated` timestamp
└── Step 6: Store market snapshots:
    └── Insert price data into `market_snapshots` table for history
```

### P&L Calculation Logic
```python
# For each open position:
if action == 'buy_yes':
    current_price = market_data['yes_price']
elif action == 'buy_no':
    current_price = market_data['no_price']

# Calculate position P&L
position_pnl = (current_price - entry_price) * amount

# Update portfolio total P&L
portfolio_total_pnl += position_pnl
```

---

## 🗄️ Database Tables Used in Flow

### During Trading Cycle:
1. **`events`** - Stores filtered trading events
2. **`markets`** - Stores filtered markets with current prices
3. **`trading_signals`** - Stores generated signals before execution
4. **`trades`** - Stores executed trade history (append-only)
5. **`portfolio_positions`** - Stores current open positions
6. **`portfolio_state`** - Stores current portfolio balance and P&L

### During Price Updates:
1. **`portfolio_positions`** - Updated with current P&L
2. **`portfolio_state`** - Updated with total P&L
3. **`market_snapshots`** - New entries created for price history

### For Historical Records:
1. **`portfolio_history`** - Daily portfolio snapshots
2. **`signal_archives`** - Monthly signal archives

---

## ⚡ Real-Time vs Batch Operations

### Real-Time Operations:
- **Price Updates**: Every 5 minutes (background thread)
- **Portfolio P&L**: Updated with each price refresh
- **Market Snapshots**: Created every 5 minutes for active markets

### Batch Operations:
- **Trading Cycle**: Typically run once per day or on-demand
- **Portfolio History**: Created once per day after trading cycle
- **Signal Archives**: Created monthly from old signals

---

## 🔗 API Call Sequence

The Trading Controller orchestrates the following API calls in order:

```python
# 1. Export Events
GET http://localhost:8000/events/export-all-active-events-db

# 2. Filter Events  
GET http://localhost:8000/events/filter-trading-candidates-db?min_liquidity=10000&min_volume=50000

# 3. Filter Markets
GET http://localhost:8001/markets/export-filtered-markets-db?min_liquidity=10000&min_volume=50000

# 4. Generate Signals
GET http://localhost:8002/strategy/generate-signals

# 5. Execute Trades
GET http://localhost:8003/paper-trading/execute-signals

# 6. Get Portfolio (for snapshot)
GET http://localhost:8003/paper-trading/portfolio
```

---

## 🛡️ Error Handling and Recovery

### Price Update Failures:
- Continues running despite individual market price fetch failures
- Logs errors but doesn't stop the background thread
- Skips markets with price parsing errors

### Trading Cycle Failures:
- Stops at first failure point and returns error details
- Previous successful steps remain completed
- Can be restarted from failed step

### Database Connection Issues:
- All controllers handle database connection errors gracefully
- Portfolio operations fail fast if database is unavailable
- Price updater continues trying and logs errors

---

## 📊 Key Metrics Tracked

### Portfolio Metrics:
- **Balance**: Available cash for trading
- **Total Invested**: Money currently in positions
- **Total P&L**: Unrealized profit/loss on open positions
- **Trade Count**: Total number of executed trades

### Performance Metrics:
- **Win Rate**: Percentage of profitable trades
- **Average P&L**: Average profit/loss per trade
- **Portfolio Growth**: Change in total value over time
- **Signal Execution Rate**: Percentage of signals that became trades

---

## 🚀 Starting the System

1. **Start all controllers** in order (ports 8000-8004)
2. **Paper Trading Controller** automatically starts the Price Updater
3. **Run trading cycle** via Trading Controller API
4. **Monitor portfolio** through Paper Trading Controller API
5. **Price updates** continue automatically in background

---

*Last Updated: 2025-10-28*
*System Version: 1.0*