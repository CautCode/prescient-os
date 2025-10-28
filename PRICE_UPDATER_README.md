# Price Updater - Setup & Usage Guide

## What It Does

The Price Updater is a **background thread** that automatically updates your portfolio's P&L by fetching current market prices from Polymarket API every 5 minutes (configurable).

### Problem It Solves
Without this, your portfolio P&L only updates once per trading cycle (e.g., daily). Market prices change constantly, so your portfolio value would be "frozen" and inaccurate between cycles.

### How It Works
1. Runs in the background when `paper_trading_controller.py` starts
2. Every 5 minutes (default), fetches current prices for all markets with open positions
3. Recalculates P&L based on current prices
4. Automatically saves updated portfolio

---

## Setup

### 1. Create `.env` File

Copy the example environment file:
```bash
cp .env.example .env
```

### 2. Configure Update Interval (Optional)

Edit `.env` file:
```bash
# Update every 5 minutes (default)
PRICE_UPDATE_INTERVAL=300

# Or set to 1 minute for faster updates
# PRICE_UPDATE_INTERVAL=60

# Or 10 minutes for less frequent updates
# PRICE_UPDATE_INTERVAL=600
```

**Recommended Settings:**
- **Development/Testing**: 60 seconds (1 minute)
- **Production**: 300 seconds (5 minutes)
- **Conservative**: 600 seconds (10 minutes)

---

## How To Run

### Option 1: Run Paper Trading Controller (Automatic)

The price updater **automatically starts** when you run the paper trading controller:

```bash
# Start the paper trading controller
python -m uvicorn src.paper_trading_controller:app --reload --port 8003
```

**You'll see this in the logs:**
```
INFO: Price updater started with 300s interval
INFO: ✓ Price updater started with 300s interval
```

### Option 2: Run Full Trading System

The price updater works automatically when running the full system:

```bash
# Terminal 1: Events Controller
python -m uvicorn src.events_controller:app --reload --port 8000

# Terminal 2: Market Controller
python -m uvicorn src.market_controller:app --reload --port 8001

# Terminal 3: Strategy Controller
python -m uvicorn src.trading_strategy_controller:app --reload --port 8002

# Terminal 4: Paper Trading Controller (with price updater)
python -m uvicorn src.paper_trading_controller:app --reload --port 8003

# Terminal 5: Trading Controller (orchestrator)
python -m uvicorn src.trading_controller:app --reload --port 8004
```

---

## API Endpoints

### Check Price Updater Status

```bash
GET http://localhost:8003/paper-trading/status
```

**Response:**
```json
{
  "timestamp": "2025-10-27T10:30:00",
  "portfolio_exists": true,
  "portfolio_balance": 9500.0,
  "open_positions": 5,
  "total_trades": 10,
  "price_updater_running": true,
  "price_update_interval": 300,
  "last_price_update": "2025-10-27T10:25:00"
}
```

### Manually Trigger Price Update

You can force an immediate price update without waiting for the interval:

```bash
GET http://localhost:8003/paper-trading/update-prices
```

**Response:**
```json
{
  "message": "Price update completed",
  "portfolio_pnl": 125.50,
  "open_positions": 5,
  "last_price_update": "2025-10-27T10:30:15",
  "timestamp": "2025-10-27T10:30:15"
}
```

---

## Monitoring

### Watch Logs in Real-Time

When the price updater runs, you'll see logs like this:

```
INFO: Updating prices for 5 markets with open positions...
DEBUG: Fetching batch 1: https://gamma-api.polymarket.com/markets?id=...
DEBUG:   market_123: YES=0.6520, NO=0.3480
DEBUG:   market_456: YES=0.7100, NO=0.2900
INFO: ✓ Fetched prices for 5/5 markets
DEBUG:   Position market_123: entry=0.6500, current=0.6520, P&L=$2.00
DEBUG:   Position market_456: entry=0.7000, current=0.7100, P&L=$10.00
INFO: Updated P&L for 5 open positions
INFO: ✓ Updated portfolio P&L: $125.50
```

### Check Portfolio P&L Anytime

```bash
GET http://localhost:8003/paper-trading/portfolio
```

**Response:**
```json
{
  "message": "Current portfolio retrieved",
  "portfolio": {
    "balance": 9500.0,
    "positions": [...],
    "total_invested": 500.0,
    "total_profit_loss": 125.50,
    "last_price_update": "2025-10-27T10:30:15"
  },
  "summary": {
    "total_value": 9625.50,
    "open_positions": 5,
    "total_invested": 500.0,
    "unrealized_pnl": 125.50
  }
}
```

---

## Testing

### Test 1: Verify Price Updater Is Running

```bash
# Check status
curl http://localhost:8003/paper-trading/status | jq

# Look for:
# "price_updater_running": true
# "price_update_interval": 300
```

### Test 2: Force Manual Update

```bash
# Trigger immediate update
curl http://localhost:8003/paper-trading/update-prices | jq

# Check the P&L changed
curl http://localhost:8003/paper-trading/portfolio | jq '.summary.unrealized_pnl'
```

### Test 3: Watch Price Changes Over Time

```bash
# Run this script to monitor P&L every minute
watch -n 60 'curl -s http://localhost:8003/paper-trading/portfolio | jq ".summary"'
```

Output:
```json
{
  "total_value": 9625.50,
  "open_positions": 5,
  "total_invested": 500.0,
  "unrealized_pnl": 125.50
}

# 1 minute later...
{
  "total_value": 9632.75,
  "open_positions": 5,
  "total_invested": 500.0,
  "unrealized_pnl": 132.75
}
```

---

## Troubleshooting

### Price Updater Not Running

**Check 1: Is the controller running?**
```bash
curl http://localhost:8003/
```

**Check 2: Check status endpoint**
```bash
curl http://localhost:8003/paper-trading/status | jq '.price_updater_running'
```

If `false`, restart the paper trading controller.

### No Price Updates

**Issue**: P&L not changing

**Solutions**:
1. **No open positions** - Price updater only runs if you have open positions
   ```bash
   curl http://localhost:8003/paper-trading/status | jq '.open_positions'
   ```

2. **Market prices not changing** - Polymarket prices might be stable
   - Manually check market prices on Polymarket.com

3. **API errors** - Check logs for errors fetching from Polymarket API

### Price Update Interval Too Long

Change in `.env` file:
```bash
# Change from 5 minutes to 1 minute
PRICE_UPDATE_INTERVAL=60
```

Then restart:
```bash
# Stop the server (Ctrl+C)
# Start it again
python -m uvicorn src.paper_trading_controller:app --reload --port 8003
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│   Paper Trading Controller (FastAPI)           │
│                                                 │
│   ┌─────────────────────────────────┐          │
│   │  Price Updater Background Thread │          │
│   │                                   │          │
│   │  Every 5 minutes:                │          │
│   │  1. Load portfolio                │          │
│   │  2. Get open positions            │          │
│   │  3. Fetch current prices from API │ ─────┐  │
│   │  4. Recalculate P&L               │      │  │
│   │  5. Save portfolio                │      │  │
│   └─────────────────────────────────┘      │  │
│                                             │  │
└─────────────────────────────────────────────┼──┘
                                              │
                                              ▼
                            ┌──────────────────────────┐
                            │  Polymarket API          │
                            │  gamma-api.polymarket.com│
                            └──────────────────────────┘
```

---

## Files Created/Modified

### New Files
- ✅ `src/price_updater.py` - Background thread implementation
- ✅ `.env.example` - Environment variable template
- ✅ `PRICE_UPDATER_README.md` - This file

### Modified Files
- ✅ `src/paper_trading_controller.py` - Added startup/shutdown hooks
  - Lines 20-35: Import and lifecycle events
  - Lines 469-499: New `/update-prices` endpoint
  - Lines 501-556: Enhanced `/status` endpoint

---

## Next Steps

### Phase 2: Price History Database (Optional)

Once you're comfortable with periodic updates, consider implementing Solution 2 from [paper_trade.md](paper_trade.md):

- Store all price updates in PostgreSQL
- Track historical P&L over time
- Build analytics dashboard
- Enable backtesting

See [postgresql.md](postgresql.md) for the database migration plan.

---

## Quick Start Checklist

- [ ] Copy `.env.example` to `.env`
- [ ] (Optional) Adjust `PRICE_UPDATE_INTERVAL` in `.env`
- [ ] Start paper trading controller: `python -m uvicorn src.paper_trading_controller:app --reload --port 8003`
- [ ] Verify price updater is running: `curl http://localhost:8003/paper-trading/status`
- [ ] Execute some trades (run full trading cycle)
- [ ] Watch P&L update automatically every 5 minutes
- [ ] (Optional) Force manual update: `curl http://localhost:8003/paper-trading/update-prices`

---

**Version**: 1.0
**Last Updated**: 2025-10-27
**Implementation**: Solution 1 from paper_trade.md
