# Prescient OS - Trading System Runbook

## Table of Contents
1. [System Overview](#system-overview)
2. [One-Time Setup](#one-time-setup)
3. [Daily Startup Procedure](#daily-startup-procedure)
4. [Running Your First Trade Cycle](#running-your-first-trade-cycle)
5. [Monitoring & Status Checks](#monitoring--status-checks)
6. [Shutdown Procedure](#shutdown-procedure)
7. [Troubleshooting](#troubleshooting)

---

## System Overview

### What This System Does

Prescient OS is an **automated paper trading system** for Polymarket prediction markets. It runs a complete trading cycle that:

1. **Fetches live events** from Polymarket API
2. **Filters markets** based on liquidity, volume, and other criteria
3. **Generates trading signals** using a >50% probability strategy
4. **Executes virtual trades** with paper money (no real funds)
5. **Tracks P&L** in real-time with automatic price updates every 5 minutes
6. **Maintains portfolio history** for performance analysis

### Architecture (5 Microservices)

The system runs **5 independent FastAPI servers** that communicate via HTTP:

```
┌─────────────────────────────────────────────────────────────┐
│                    MAIN TRADING CONTROLLER                   │
│                    (Port 8004)                               │
│         Orchestrates the entire trading cycle                │
└─────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Events          │  │ Markets         │  │ Strategy        │
│ Controller      │  │ Controller      │  │ Controller      │
│ (Port 8000)     │  │ (Port 8001)     │  │ (Port 8002)     │
│                 │  │                 │  │                 │
│ Fetches &       │  │ Filters markets │  │ Generates       │
│ filters events  │  │ from events     │  │ buy/sell signals│
└─────────────────┘  └─────────────────┘  └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Paper Trading   │
                    │ Controller      │
                    │ (Port 8003)     │
                    │                 │
                    │ Executes trades │
                    │ & manages P&L   │
                    └─────────────────┘
```

### Portfolio Architecture (NEW!)

The system now supports **multiple independent portfolios**, each with:
- Separate capital allocation
- Independent P&L tracking
- Portfolio-specific strategy configuration
- Isolated trading activity

**Current Status**: After migration, you have a fresh database with **NO portfolios yet**.

---

## One-Time Setup

### Prerequisites

- Windows 10/11
- Python 3.8 or higher
- PostgreSQL 12 or higher installed and running
- Chrome browser (for API documentation)

### Step 1: Database Setup

**IMPORTANT**: Your database was recently rebuilt with the new portfolio schema. All old data is gone.

1. **Verify PostgreSQL is running**:
   ```bash
   # In PowerShell or Command Prompt
   psql -U postgres -c "SELECT version();"
   ```

2. **Verify database exists**:
   ```bash
   psql -U postgres -c "\l" | findstr prescient_os
   ```

   You should see `prescient_os` in the list.

3. **Verify schema is correct**:
   ```bash
   psql -U postgres -d prescient_os -c "\dt"
   ```

   You should see these tables:
   - `portfolios` (NEW - replaces old portfolio_state)
   - `portfolio_positions`
   - `trades`
   - `trading_signals`
   - `portfolio_history`
   - `events`
   - `markets`
   - `market_snapshots`

### Step 2: Python Environment Setup

1. **Clone/navigate to project directory**:
   ```bash
   cd C:\Users\berar\Desktop\prescient-os
   ```

2. **Create virtual environment** (if not already done):
   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment**:
   ```bash
   venv\Scripts\activate
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Install PostgreSQL driver**:
   ```bash
   pip install psycopg2-binary sqlalchemy
   ```

### Step 3: Environment Configuration

1. **Copy `.env.example` to `.env`**:
   ```bash
   copy .env.example .env
   ```

2. **Edit `.env` file** with your PostgreSQL credentials:
   ```bash
   notepad .env
   ```

   Verify these settings:
   ```
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=prescient_os
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=381c286a176e40d99abd7ed87e0cab93

   PRICE_UPDATE_INTERVAL=300  # 5 minutes (in seconds)
   PYTHON_LOG_LEVEL=INFO
   ```

### Step 4: Create Your First Portfolio

**CRITICAL**: The system requires at least one active portfolio to function.

Open a Python shell and run:

```python
from src.db.operations import create_portfolio

# Create default portfolio with $10,000 starting capital
portfolio_id = create_portfolio({
    'name': 'Default Portfolio',
    'description': 'Primary trading portfolio',
    'strategy_type': 'momentum',
    'initial_balance': 10000.00,
    'current_balance': 10000.00,
    'strategy_config': {
        'min_confidence': 0.75,
        'market_types': ['politics', 'crypto']
    }
})

print(f"✅ Created portfolio ID: {portfolio_id}")
```

**Alternative**: Use the API after servers start (see Step 5 of Daily Startup).

---

## Daily Startup Procedure

### Step 1: Start All Servers

1. **Open Command Prompt** in project directory:
   ```bash
   cd C:\Users\berar\Desktop\prescient-os
   ```

2. **Run the startup script**:
   ```bash
   start_servers.bat
   ```

3. **Choose logging mode**:
   - Type `n` for normal mode (recommended for daily use)
   - Type `y` for debug mode (detailed logging, use for troubleshooting)

4. **Wait for startup**:
   - Script opens 5 command windows (one per controller)
   - Wait ~10 seconds for all servers to initialize
   - Chrome opens 5 API documentation tabs automatically

### Step 2: Verify All Services Are Online

Visit the main controller status endpoint:

**Browser**: http://localhost:8004/trading/status

You should see:
```json
{
  "system_health": "healthy",
  "health_summary": {
    "online_components": 4,
    "total_components": 4,
    "health_percentage": 100.0
  }
}
```

If any component shows "offline", check that server's command window for errors.

### Step 3: Verify Portfolio Exists

**Browser**: http://localhost:8003/portfolios/list

You should see at least one active portfolio. If empty, create one using the API documentation at http://localhost:8003/docs:

1. Find `POST /portfolios/create`
2. Click "Try it out"
3. Enter portfolio data:
   ```json
   {
     "name": "Default Portfolio",
     "description": "Primary trading portfolio",
     "strategy_type": "momentum",
     "initial_balance": 10000,
     "strategy_config": {
       "min_confidence": 0.75
     }
   }
   ```
4. Click "Execute"

### Step 4: Verify Price Updater Is Running

**Browser**: http://localhost:8003/paper-trading/status

Check that:
```json
{
  "price_updater_running": true,
  "price_update_interval": 300
}
```

The price updater automatically updates open position prices every 5 minutes.

### Step 5: Check Current Portfolio State

**Browser**: http://localhost:8003/paper-trading/portfolio

You should see your portfolio with starting balance and zero positions.

---

## Running Your First Trade Cycle

### Understanding the Trading Cycle

A complete trading cycle executes these steps:

1. **Export Events** - Fetch all active events from Polymarket
2. **Filter Events** - Keep only high-liquidity, high-volume events
3. **Filter Markets** - Extract tradable markets with 50-60% conviction
4. **Generate Signals** - Create buy signals for >50% probability outcomes
5. **Execute Trades** - Place virtual trades (deduct from balance)
6. **Update Prices** - Calculate current P&L on open positions
7. **Create Snapshot** - Save daily portfolio state for history

### Option A: Run Full Automated Cycle (Recommended)

**Browser**: Visit http://localhost:8004/docs

1. Find `GET /trading/run-full-cycle`
2. Click "Try it out"
3. Use default parameters or customize:
   ```
   event_min_liquidity: 10000      # Minimum $10k event liquidity
   event_min_volume: 50000          # Minimum $50k event volume
   min_liquidity: 10000             # Minimum $10k market liquidity
   min_volume: 50000                # Minimum $50k market volume
   min_market_conviction: 0.5       # Markets with 50%+ probability
   max_market_conviction: 0.6       # But not >60% (too risky)
   ```
4. Click "Execute"

**Expected Results**:
- Cycle takes 30-90 seconds depending on Polymarket API response
- Returns detailed results for all 7 steps
- Check `execution_summary` to see how many trades executed

### Option B: Run Portfolio-Specific Cycle

If you have multiple portfolios and want to trade only one:

**Browser**: http://localhost:8004/docs

1. Find `GET /trading/run-portfolio-cycle`
2. Enter `portfolio_id` (e.g., `1`)
3. Set filtering parameters (same as above)
4. Click "Execute"

### Option C: Run All Portfolios

**Browser**: http://localhost:8004/docs

1. Find `GET /trading/run-all-portfolios`
2. This runs cycles for ALL active portfolios
3. Markets are fetched once (shared), then each portfolio trades independently

### What Happens During a Trade?

When a signal is executed:

1. **Balance Deduction**: `$100` deducted from portfolio balance (default trade size)
2. **Position Created**: Open position tracking entry price and P&L
3. **Trade Recorded**: Full trade history saved to database
4. **Signal Marked**: Trading signal marked as executed

### Viewing Trade Results

After running a cycle:

1. **Check executed trades**:
   - Browser: http://localhost:8003/paper-trading/trades-history

2. **Check open positions**:
   - Browser: http://localhost:8003/paper-trading/portfolio
   - Shows current positions with live P&L

3. **Check portfolio performance**:
   - Browser: http://localhost:8004/trading/performance-summary

---

## Monitoring & Status Checks

### Real-Time Price Updates

The system **automatically** updates prices every 5 minutes (configurable in `.env`).

**Manual price update** (if needed):
- Browser: http://localhost:8003/price-updater/update
- Or visit http://localhost:8003/docs and find `GET /price-updater/update`

### Portfolio Dashboard

**Current Portfolio State**:
```
http://localhost:8003/paper-trading/portfolio?portfolio_id=1
```

Shows:
- Current balance
- Total invested
- Total P&L (unrealized)
- Open positions with current prices
- Total portfolio value

### Trading History

**All Trades**:
```
http://localhost:8003/paper-trading/trades-history?portfolio_id=1&limit=50
```

### Performance Tracking

**Historical Performance**:
```
http://localhost:8004/trading/performance-summary
```

Shows:
- Portfolio value over time
- Total trades executed
- Win/loss breakdown
- Daily snapshots

### System Health Check

**Overall Status**:
```
http://localhost:8004/trading/status
```

Checks all 4 microservices and reports health percentage.

---

## Shutdown Procedure

### Graceful Shutdown

1. **Run the shutdown script**:
   ```bash
   stop_servers.bat
   ```

   This:
   - Kills all Python/uvicorn processes
   - Closes all controller windows
   - Safely terminates the price updater

2. **Verify shutdown**:
   - All 5 command windows should close
   - Check Task Manager - no `python.exe` or `uvicorn.exe` processes

### Manual Shutdown (If Script Fails)

1. Close each command window manually (all 5)
2. Open Task Manager (Ctrl+Shift+Esc)
3. Find and end all `python.exe` processes
4. Find and end all `uvicorn.exe` processes

---

## Troubleshooting

### Problem: "No active portfolios found"

**Cause**: Database has no portfolios (fresh database after migration)

**Solution**: Create a portfolio (see Step 4 of One-Time Setup)

---

### Problem: Server Won't Start - "Address already in use"

**Cause**: Port is already occupied by a previous server instance

**Solution**:
```bash
# Kill all Python processes
taskkill /f /im python.exe
taskkill /f /im uvicorn.exe

# Restart servers
start_servers.bat
```

---

### Problem: "Error connecting to database"

**Cause**: PostgreSQL is not running or credentials are wrong

**Solution**:

1. **Check PostgreSQL is running**:
   ```bash
   # In Command Prompt
   sc query postgresql-x64-14  # Adjust version number
   ```

2. **Start PostgreSQL** (if stopped):
   ```bash
   net start postgresql-x64-14
   ```

3. **Verify credentials in `.env`** match your PostgreSQL installation

4. **Test connection**:
   ```bash
   psql -U postgres -d prescient_os -c "SELECT 1;"
   ```

---

### Problem: "No trading signals found"

**Cause**: Market filtering parameters are too restrictive, or Polymarket has no matching markets

**Solution**:

1. **Lower filtering thresholds** in the trading cycle:
   ```
   min_liquidity: 5000          # Lower from 10000
   min_volume: 25000            # Lower from 50000
   max_market_conviction: 0.7   # Increase from 0.6
   ```

2. **Check filtered markets**:
   - Browser: http://localhost:8001/docs
   - Run `GET /markets/export-filtered-markets-db` with lower thresholds

---

### Problem: Price updater not running

**Cause**: Paper Trading Controller failed to start the background thread

**Solution**:

1. **Check Paper Trading status**:
   - Browser: http://localhost:8003/paper-trading/status

2. **Restart Paper Trading Controller**:
   - Close the "Paper Trading Controller" window
   - Start it manually:
     ```bash
     venv\Scripts\activate
     uvicorn src.paper_trading_controller:app --reload --port 8003
     ```

3. **Verify in startup logs**:
   ```
   ✓ Price updater started with 300s interval
   ```

---

### Problem: Trades executing but P&L stays at $0

**Cause**: Price updater hasn't run yet, or market prices unavailable

**Solution**:

1. **Manually trigger price update**:
   - Browser: http://localhost:8003/price-updater/update

2. **Wait 5 minutes** for automatic update

3. **Check market snapshots**:
   ```bash
   psql -U postgres -d prescient_os -c "SELECT COUNT(*) FROM market_snapshots;"
   ```

---

### Problem: API returns 500 Internal Server Error

**Cause**: Various - check server logs in the command window

**Solution**:

1. **Look at the specific controller's command window** for detailed error
2. **Enable DEBUG mode**:
   - Stop servers: `stop_servers.bat`
   - Restart with debug: `start_servers.bat` → type `y`
3. **Check logs** for full stack traces
4. **Common issues**:
   - Database connection errors → check PostgreSQL
   - Missing portfolio → create one
   - Invalid API response from Polymarket → wait and retry

---

### Problem: Chrome doesn't open automatically

**Cause**: Script can't find Chrome or browser is set to different default

**Solution**:

1. **Manually open API docs**:
   - http://localhost:8000/docs (Events)
   - http://localhost:8001/docs (Markets)
   - http://localhost:8002/docs (Strategy)
   - http://localhost:8003/docs (Paper Trading)
   - http://localhost:8004/docs (Main Controller)

2. **Edit start_servers.bat** line 94-98 to use your browser:
   ```batch
   start firefox "http://localhost:8000/docs"
   # or
   start msedge "http://localhost:8000/docs"
   ```

---

## Daily Workflow Checklist

### Morning Routine (5 minutes)

- [ ] Start servers: `start_servers.bat`
- [ ] Verify system health: http://localhost:8004/trading/status
- [ ] Check portfolio state: http://localhost:8003/paper-trading/portfolio
- [ ] Review yesterday's trades: http://localhost:8003/paper-trading/trades-history

### Run Trading Cycle (2 minutes)

- [ ] Visit: http://localhost:8004/docs
- [ ] Execute: `GET /trading/run-full-cycle`
- [ ] Review results: Check execution_summary

### Afternoon Check (1 minute)

- [ ] Check P&L: http://localhost:8003/paper-trading/portfolio
- [ ] Verify price updater is working (look for updated `total_profit_loss`)

### Evening Shutdown (1 minute)

- [ ] Run: `stop_servers.bat`
- [ ] Verify all windows closed

---

## Advanced: Running Automated Cycles

### Option 1: Windows Task Scheduler

Create a scheduled task to run the trading cycle automatically:

1. **Create a batch file** `run_daily_cycle.bat`:
   ```batch
   @echo off
   curl http://localhost:8004/trading/run-full-cycle > daily_cycle_log.txt
   ```

2. **Schedule in Task Scheduler**:
   - Open Task Scheduler
   - Create Basic Task
   - Trigger: Daily at 9:00 AM
   - Action: Start program → `run_daily_cycle.bat`

### Option 2: Continuous Monitoring

Leave servers running 24/7 with automatic price updates every 5 minutes.

**Recommended**:
- Keep `start_servers.bat` running
- Price updater handles automatic P&L updates
- Run manual cycles when you want to trade

---

## Next Steps

Once you're comfortable with basic operations:

1. **Create Multiple Portfolios** - Test different strategies simultaneously
2. **Adjust Trading Parameters** - Fine-tune liquidity/volume filters
3. **Analyze Performance** - Use performance summary to track wins/losses
4. **Monitor Market Snapshots** - Review historical price data
5. **Export Data** - Query PostgreSQL directly for custom analysis

---

## Support & Resources

### API Documentation
- Events: http://localhost:8000/docs
- Markets: http://localhost:8001/docs
- Strategy: http://localhost:8002/docs
- Paper Trading: http://localhost:8003/docs
- Main Controller: http://localhost:8004/docs

### Database Access
```bash
psql -U postgres -d prescient_os
```

### Useful SQL Queries

**List all portfolios**:
```sql
SELECT portfolio_id, name, current_balance, total_profit_loss, status
FROM portfolios;
```

**View recent trades**:
```sql
SELECT portfolio_id, market_question, action, amount, entry_price, status
FROM trades
ORDER BY timestamp DESC
LIMIT 10;
```

**Portfolio performance over time**:
```sql
SELECT snapshot_date, balance, total_invested, total_profit_loss, total_value
FROM portfolio_history
WHERE portfolio_id = 1
ORDER BY snapshot_date DESC;
```

---

## Key Takeaways

✅ **5 microservices** must be running for the system to work
✅ **At least 1 portfolio** must exist in the database
✅ **Price updater** runs automatically every 5 minutes
✅ **Trading cycles** can be run on-demand or scheduled
✅ **All data** is stored in PostgreSQL (no JSON files)
✅ **Paper money only** - no real funds at risk

**Ready to trade!** Start your servers and run your first cycle.
