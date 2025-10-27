# MVP Trading System Implementation Plan

## Architecture Overview

Based on your existing `events_controller.py`, we'll build a modular trading system that leverages your current event filtering capabilities and extends them with market data, trading strategies, and paper trading.

## Complete File Structure (MVP with JSON + CSV Exports)

```
prescient-os/
├── src/
│   ├── events_controller.py          # (existing) Enhanced with JSON exports
│   ├── market_controller.py          # Market data fetching & price monitoring
│   ├── trading_strategy.py           # Basic trading logic (>50% buy strategy)
│   ├── paper_trading.py              # Paper trading simulation & portfolio tracking
│   ├── portfolio_manager.py          # Position tracking & risk management
│   ├── trading_controller.py         # Main orchestration controller
│   ├── csv_exports.py                # Centralized CSV export functions
│   └── models/
│       ├── market.py                 # Market data models
│       ├── trade.py                  # Trade & position models
│       └── portfolio.py              # Portfolio & performance models
├── data/
│   ├── events/
│   │   ├── filtered_events.json         # Filtered events (OVERWRITE daily)
│   │   ├── filtered_markets.json        # Individual markets (OVERWRITE daily)
│   │   └── raw_events_backup.json       # Optional: backup (OVERWRITE daily)
│   ├── markets/
│   │   ├── market_cache.json            # Current market prices (OVERWRITE daily)
│   │   └── daily_prices_YYYY-MM-DD.json # Daily snapshots (NEW FILE each day)
│   ├── trades/
│   │   ├── current_signals.json         # Latest trading signals (OVERWRITE daily)
│   │   ├── paper_trades.json            # All executed trades (APPEND ONLY - never overwrite)
│   │   └── portfolio.json               # Current balance & positions (OVERWRITE daily)
│   ├── history/                         # Historical tracking for performance analysis
│   │   ├── portfolio_history.json       # Daily portfolio snapshots (APPEND ONLY)
│   │   └── signals_archive_YYYY-MM.json # Monthly signal history (NEW FILE monthly)
│   └── exports/                         # Auto-generated CSV files (REGENERATE daily)
│       ├── events_filtered.csv          # Filtered events (human-readable)
│       ├── markets_extracted.csv        # Individual markets from events
│       ├── markets_current.csv          # Current market prices & signals
│       ├── signals_current.csv          # Latest trading signals
│       ├── trades_summary.csv           # All trades with key metrics
│       ├── portfolio_history.csv        # Daily portfolio snapshots
│       ├── positions_current.csv        # Current open positions with P&L
│       └── performance_daily.csv        # Daily returns & cumulative performance
├── logs/
│   └── trading_log_YYYY-MM-DD.txt      # Daily activity logs
└── (existing files: main.py, requirements.txt, etc.)
```

**Data Flow Summary:**
- **JSON files**: Structured data for the trading system to process
- **CSV files**: Auto-generated exports for quick human analysis
- **Logs**: Text files for debugging and audit trails
- **Daily files**: Time-stamped snapshots for historical analysis

## 📅 Data Persistence Strategy

### Files That Get OVERWRITTEN Daily (Latest State Only):
- `filtered_events.json` - Latest filtered events from morning refresh
- `filtered_markets.json` - Latest individual markets 
- `market_cache.json` - Current market prices (refreshed multiple times daily)
- `current_signals.json` - Latest trading signals from strategy
- `portfolio.json` - Current balance and open positions
- **All CSV exports** - Regenerated from current JSON state

### Files That ACCUMULATE/PERSIST Forever:
- `paper_trades.json` - **APPEND ONLY** - Complete trade history log
- `portfolio_history.json` - **APPEND ONLY** - Daily portfolio snapshots
- `daily_prices_YYYY-MM-DD.json` - **NEW FILE EACH DAY** - Price history
- `signals_archive_YYYY-MM.json` - **NEW FILE MONTHLY** - Signal history
- `trading_log_YYYY-MM-DD.txt` - **NEW FILE EACH DAY** - Activity logs

### Daily Data Management Workflow:
```
Morning (9 AM):
1. Overwrite events/markets JSONs with fresh data
2. Regenerate all CSV exports from current state

Throughout Day:
3. Append new trades to paper_trades.json (never overwrite)
4. Update portfolio.json with current positions

End of Day (6 PM):
5. Create daily_prices_2024-10-20.json snapshot
6. Append daily summary to portfolio_history.json
7. Archive signals to monthly signals_archive_2024-10.json
8. Final CSV export regeneration
```

### Performance Analysis Strategy:
- **Short-term**: Use regenerated CSV exports for daily analysis
- **Long-term**: Use accumulated JSON files for historical backtesting
- **Audit trail**: Complete trade history always preserved in paper_trades.json

## Implementation Phases

### Phase 0: Events Controller Enhancement (Foundation)
**Goal**: Upgrade existing events controller to support JSON storage + CSV exports for the trading pipeline

**Current State Analysis**: 
- ✅ Excellent filtering logic in `apply_trading_filters()` - this is perfect for trading
- ✅ Comprehensive CSV export with all event fields 
- ✅ Good error handling and logging
- ⚠️ No JSON export capability
- ⚠️ Hardcoded field list in CSV export (lines 529-530) - hard to maintain
- ⚠️ No market-level data (only event-level)

**Target State**: Enhanced to support JSON storage with automatic CSV exports for trading system integration

**Specific Improvements Needed**:

1. **Add JSON Export Functionality** (Minimal Code Changes)
   - New endpoint: `/events/export-filtered-json` 
   - Reuse existing `apply_trading_filters()` logic
   - Save to `data/events/filtered_events.json`
   - Auto-generate simplified CSV: `data/exports/events_filtered.csv`

2. **Fix CSV Export Maintainability**
   - Replace hardcoded 80+ field list with dynamic field extraction
   - Use DataFrame.columns for automatic field detection
   - Reduces code from 80 lines to ~5 lines

3. **Add Market-Level Data Export**
   - Current exports only show event-level data
   - Add `/events/export-markets-json` to extract individual markets from events
   - Critical for trading system (events can have multiple markets)

4. **Enhanced Directory Structure**:
   ```
   data/
   ├── events/
   │   ├── filtered_events.json        # Trading-ready events
   │   ├── filtered_markets.json       # Individual markets for trading  
   │   └── raw_events_backup.json      # Optional: full API response backup
   ├── exports/
   │   ├── events_filtered.csv         # Simplified event view (key fields only)
   │   └── markets_extracted.csv       # All markets from filtered events
   └── (existing timestamped CSV files remain unchanged)
   ```

**New API Endpoints** (3 new endpoints, ~50 lines of code):
```python
@app.get("/events/export-filtered-json")
async def export_filtered_events_json():
    # Use existing filter_trading_candidates() logic
    # Save JSON + generate clean CSV export

@app.get("/events/export-markets-json") 
async def export_markets_from_events():
    # Extract individual markets from filtered events
    # Save as JSON + CSV for trading system

@app.get("/events/refresh-all-exports")
async def refresh_all_exports():
    # Regenerate all JSON + CSV exports
    # One-click refresh for trading system
```

**Code Improvements** (Quality of Life):
1. **Dynamic CSV Field Generation**: Replace 80-line hardcoded field list with:
   ```python
   # Instead of hardcoded fieldnames list
   fieldnames = list(events_data[0].keys()) if events_data else []
   ```

2. **Market Extraction Helper**: Add function to extract markets from events:
   ```python
   def extract_markets_from_events(events):
       markets = []
       for event in events:
           for market in event.get('markets', []):
               markets.append({
                   'event_id': event['id'],
                   'market_id': market['id'], 
                   'market_slug': market['slug'],
                   # ... other market fields
               })
       return markets
   ```

3. **Consistent Directory Creation**: Add helper for directory management:
   ```python
   def ensure_data_directories():
       os.makedirs("data/events", exist_ok=True)
       os.makedirs("data/exports", exist_ok=True)
   ```

**Why These Changes Matter for Trading**:
- **Market-level data**: Events can have multiple markets - you need individual market data for trading
- **JSON format**: Trading system needs structured data, not CSV parsing
- **Maintainable code**: Dynamic field generation prevents breaking when API changes
- **Clean exports**: Simplified CSV views for quick analysis

**Implementation Priority**:
1. **First**: Add market extraction (critical for trading)
2. **Second**: Add JSON exports (enables trading system)  
3. **Third**: Clean up CSV export code (quality of life)

**Success Criteria**:
- ✅ Existing CSV functionality continues to work unchanged
- ✅ Individual markets available as JSON for trading system
- ✅ Clean, focused CSV exports for human analysis  
- ✅ Maintainable code that won't break with API changes

---

### Phase 1: Market Data Infrastructure (Foundation)
**Goal**: Get market prices and trading-ready data for filtered events

**Components to Build**:
1. **Market Controller** (`src/market_controller.py`)
   - Fetch individual market data from Polymarket API
   - Save to `data/market_cache.json` and daily snapshots
   - Get current prices (bid/ask spreads)
   - API endpoints:
     - `/markets/refresh` - Fetch latest prices for filtered events
     - `/markets/current` - Get cached market data
     - `/markets/export-csv` - Export current markets to CSV

2. **Market Data Models** (`src/models/market.py`)
   - Simple dataclasses for market data
   - JSON serialization helpers
   - CSV export functions

**MVP Data Flow**:
1. Use existing `apply_trading_filters()` to get event IDs
2. Fetch market data from Polymarket API
3. Save to `data/market_cache.json`
4. Auto-generate `data/exports/markets_current.csv` for quick viewing

**Success Criteria**: 
- Can fetch market prices for filtered events
- Data saved as JSON + auto-exported to CSV
- Easy to view current market state in spreadsheet

---

### Phase 2: Basic Trading Strategy (Logic)
**Goal**: Implement simple ">50% buy" strategy with proper market selection

**Components to Build**:
1. **Trading Strategy Engine** (`src/trading_strategy.py`)
   - Market selection logic (choose best market per event)
   - Price analysis (>50% threshold detection)
   - Signal generation and JSON storage
   - API endpoints:
     - `/strategy/generate-signals` - Analyze markets & generate signals
     - `/strategy/current-signals` - Get latest signals
     - `/strategy/export-signals-csv` - Export signals to CSV

2. **Simple Trade Models** (`src/models/trade.py`)
   - Basic dataclasses for signals and trades
   - JSON serialization
   - CSV export helpers

**Strategy Logic**:
```python
def generate_trading_signals(market_data):
    signals = []
    for market in market_data:
        if market['price'] > 0.50:
            signals.append({
                'timestamp': datetime.now().isoformat(),
                'market_id': market['id'],
                'market_name': market['name'],
                'action': 'buy_no',
                'amount': 100,  # Fixed $100 trades
                'confidence': market['price'] - 0.50,
                'reason': f"Price {market['price']} > 0.50"
            })
    return signals
```

**MVP Data Flow**:
1. Load current market data from `data/market_cache.json`
2. Generate trading signals based on >50% strategy
3. Save signals to `data/trades/current_signals.json`
4. Auto-export to `data/exports/signals_current.csv`

**Success Criteria**:
- Can analyze market prices and generate buy/no-buy signals
- Signals saved as JSON + exported to CSV for easy review
- Strategy parameters easily configurable

---

### Phase 3: Paper Trading System (Execution Simulation)
**Goal**: Simulate trades without real money to validate strategy performance

**Components to Build**:
1. **Paper Trading Engine** (`src/paper_trading.py`)
   - Execute signals from `current_signals.json`
   - Update `portfolio.json` with new positions/balance
   - Append trades to `paper_trades.json`
   - API endpoints:
     - `/paper-trading/execute-signals` - Execute all current signals
     - `/paper-trading/export-trades-csv` - Export trades summary
     - `/paper-trading/export-portfolio-csv` - Export portfolio history

2. **Simple Portfolio Manager** (`src/portfolio_manager.py`)
   - Load/save portfolio state from JSON
   - Calculate position P&L based on current market prices
   - Update portfolio history daily
   - Generate CSV exports for easy viewing

3. **Portfolio Models** (`src/models/portfolio.py`)
   - Simple dataclasses for positions and portfolio
   - JSON serialization
   - CSV export functions

**Paper Trading Features**:
- Start with virtual $10,000 balance in `portfolio.json`
- Fixed position size ($100 per trade)
- Track open positions with entry prices
- Auto-calculate unrealized P&L using current market prices

**MVP Data Files**:
- `data/trades/portfolio.json` - Current balance & positions (OVERWRITE daily)
- `data/trades/paper_trades.json` - All executed trades (APPEND ONLY - never overwrite)
- `data/history/portfolio_history.json` - Daily portfolio snapshots (APPEND ONLY)
- `data/exports/trades_summary.csv` - Key trade data (regenerated from paper_trades.json)
- `data/exports/portfolio_history.csv` - Daily snapshots (regenerated from portfolio_history.json)
- `data/exports/positions_current.csv` - Current open positions (regenerated from portfolio.json)

**Data Persistence Logic**:
- **paper_trades.json**: Append each executed trade - provides complete audit trail
- **portfolio.json**: Overwrite with current state - enables fast position lookups
- **portfolio_history.json**: Append daily summary - enables performance analysis over time
- **CSV exports**: Always regenerated from JSON sources - ensures consistency

**Success Criteria**:
- Can execute virtual trades based on strategy signals
- All data saved as JSON but easily viewable via CSV exports
- Portfolio performance trackable in spreadsheets

---

### Phase 4: Integration & Automation (MVP Complete)
**Goal**: Create end-to-end automated trading pipeline with easy data access

**Components to Build**:
1. **Main Trading Controller** (`src/trading_controller.py`)
   - Orchestrate entire trading workflow
   - Auto-generate all CSV exports after each cycle
   - API endpoints:
     - `/trading/run-full-cycle` - Complete trading cycle + export CSVs
     - `/trading/export-all-csv` - Regenerate all CSV exports
     - `/trading/status` - System status and latest performance metrics

2. **Complete Workflow Integration**:
   ```
   Daily Morning Routine (9 AM):
   1. Filter Events (existing) → OVERWRITE filtered_events.json + filtered_markets.json
   2. Fetch Market Data → OVERWRITE market_cache.json + CREATE daily_prices_YYYY-MM-DD.json
   3. Generate Signals → OVERWRITE current_signals.json
   4. Regenerate ALL CSV exports from current JSON state
   
   Throughout Day (Real-time):
   5. Execute Paper Trades → APPEND to paper_trades.json + UPDATE portfolio.json
   6. Update Portfolio P&L → UPDATE portfolio.json with current market prices
   
   End of Day (6 PM):
   7. Create Daily Snapshot → APPEND to portfolio_history.json
   8. Archive Signals → APPEND to signals_archive_YYYY-MM.json
   9. Final CSV Export → Regenerate all CSV files for next day analysis
   ```

3. **CSV Export Manager** (`src/csv_exports.py`)
   - Central place for all CSV export functions
   - Standardized column formats across all exports
   - Automatic export after each trading cycle

**Key CSV Exports Generated**:
- `markets_current.csv` - Current market prices and signals
- `trades_summary.csv` - All trades with key metrics
- `portfolio_history.csv` - Daily portfolio performance
- `positions_current.csv` - Open positions with P&L
- `performance_daily.csv` - Daily returns and cumulative performance

**Success Criteria**:
- Complete automated trading cycle
- All data accessible via both JSON (storage) and CSV (viewing)
- Easy performance analysis in Excel/Google Sheets
- Ready for live trading transition

---

## Technical Implementation Notes

### Leveraging Existing Code
- Your `apply_trading_filters()` function is perfect for initial event filtering
- The CSV export functionality provides the foundation for our JSON→CSV approach
- FastAPI structure is ideal for modular expansion

### Key MVP Design Principles
1. **JSON for Storage**: Flexible data structures, easy to work with programmatically
2. **CSV for Analysis**: Auto-generated exports for quick human review
3. **Modular**: Each phase builds on previous ones
4. **API-First**: Everything accessible via REST endpoints
5. **Viewable Data**: Never store data you can't easily inspect

### Data Viewing Strategy
**Daily Workflow**:
1. Run `/trading/run-full-cycle` (generates fresh data + CSV exports)
2. Open `data/exports/` folder to view latest CSV files in Excel
3. Check `trades_summary.csv` for recent trades
4. Review `portfolio_history.csv` for performance trends
5. Monitor `positions_current.csv` for open position P&L

### Recommended Phase Implementation Order
1. **Start with Phase 1**: Market data with CSV exports
2. **Phase 2**: Strategy signals with CSV exports  
3. **Phase 3**: Paper trading with CSV exports
4. **Phase 4**: Full automation + consolidated CSV exports

### Quick Start Benefits
- **Immediate feedback**: See your data in familiar CSV format
- **Easy debugging**: Compare JSON data vs CSV exports to verify logic
- **Performance analysis**: Use Excel pivot tables on CSV exports
- **No learning curve**: Work with data the same way you do now

This approach gives you the best of both worlds: programmatic flexibility with JSON and human-friendly analysis with CSV exports.

---

## Architectural Recommendations

### Better Alternatives to REST Endpoints

**Current Plan**: REST endpoints for each component
**Recommended**: Event-driven microservices with message queues

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Event Bus     │    │   Background     │    │   WebSocket     │
│   (Redis/NATS)  │◄──►│   Workers       │◄──►│   Dashboard     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       ▲                       ▲
         │                       │                       │
    ┌────▼────┐              ┌───▼───┐               ┌───▼───┐
    │ Market  │              │Trading│               │Portfolio│
    │ Service │              │Engine │               │Manager │
    └─────────┘              └───────┘               └───────┘
```

**Benefits**:
- Asynchronous processing (no blocking API calls)
- Better scalability and fault tolerance
- Real-time updates via WebSockets
- Natural separation of concerns

### Better Data Storage Than CSVs

**Current Plan**: CSV files for data persistence
**Recommended**: Hybrid approach with proper database

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                               │
├─────────────────┬─────────────────┬─────────────────────────┤
│   Time Series   │   Operational   │      Configuration      │
│   (InfluxDB)    │   (PostgreSQL)  │        (Redis)          │
├─────────────────┼─────────────────┼─────────────────────────┤
│ • Market prices │ • Events        │ • Strategy parameters   │
│ • Portfolio P&L │ • Trades        │ • Trading filters       │
│ • Performance   │ • Positions     │ • System settings       │
│   metrics       │ • User data     │ • Cache data            │
└─────────────────┴─────────────────┴─────────────────────────┘
```

**Why This Works Better**:
- **InfluxDB**: Optimized for time-series data (prices, metrics)
- **PostgreSQL**: ACID compliance for trades and positions
- **Redis**: Fast caching and real-time configuration

### Recommended Architecture Stack

```python
# Tech Stack Recommendation
{
    "message_queue": "Redis Streams",  # Event-driven communication
    "databases": {
        "operational": "PostgreSQL",   # Trades, positions, events
        "timeseries": "InfluxDB",     # Market data, performance
        "cache": "Redis"              # Fast lookups, sessions
    },
    "async_framework": "FastAPI + Celery",  # Background tasks
    "real_time": "WebSockets",        # Live updates
    "monitoring": "Prometheus + Grafana"  # System health
}
```

### Implementation Priority Changes

**Phase 1**: Database Setup + Event Architecture
1. Set up PostgreSQL for operational data
2. Implement Redis for caching and message passing
3. Create core data models with SQLAlchemy

**Phase 2**: Async Market Data Pipeline
1. Background workers for market data fetching
2. Real-time price streaming
3. Event-driven market updates

**Phase 3**: Strategy Engine as Worker Service
1. Celery tasks for strategy execution
2. Event-driven signal generation
3. Async trade execution simulation

**Phase 4**: Real-time Dashboard
1. WebSocket connections for live updates
2. Real-time portfolio tracking
3. Performance visualization

### Migration Path from Current System

1. **Keep existing CSV exports** as backup/audit trail
2. **Gradually migrate** data to proper databases
3. **Maintain API compatibility** during transition
4. **Add event bus** alongside existing REST endpoints

This architecture scales better, handles real-time data efficiently, and provides proper data persistence while maintaining your current development momentum.

---

## 🚀 SIMPLE MVP APPROACH (Start Here)

**Goal**: Get a working trading system in hours, not weeks. Use what you have, add incrementally.

### Complete MVP Data Structure

**Strategy**: JSON storage + automatic CSV exports for easy viewing

```
prescient-os/data/
├── events/                              # Phase 0: Enhanced Events Controller
│   ├── filtered_events.json               # Trading-ready events from your existing filters
│   ├── filtered_markets.json              # Individual markets extracted from events
│   └── raw_events_backup.json             # Optional: backup of full API response
├── markets/                             # Phase 1: Market Data Pipeline  
│   ├── market_cache.json                  # Current market prices & data
│   └── daily_prices_YYYY-MM-DD.json       # Daily snapshots for historical analysis
├── trades/                              # Phase 2 & 3: Strategy + Paper Trading
│   ├── current_signals.json               # Latest trading signals (OVERWRITE daily)
│   ├── paper_trades.json                  # All executed trades (APPEND ONLY - never overwrite)
│   └── portfolio.json                     # Current balance & positions (OVERWRITE daily)
├── history/                             # Historical data for performance analysis
│   ├── portfolio_history.json             # Daily portfolio snapshots (APPEND ONLY)
│   └── signals_archive_YYYY-MM.json       # Monthly signal history (NEW FILE monthly)
├── exports/                             # Auto-generated CSV files (REGENERATE daily)
│   ├── events_filtered.csv                # Events from Phase 0 (human-readable)
│   ├── markets_extracted.csv              # Markets from Phase 0 (trading targets)
│   ├── markets_current.csv                # Live prices from Phase 1
│   ├── signals_current.csv                # Strategy signals from Phase 2
│   ├── trades_summary.csv                 # Trade history from Phase 3
│   ├── portfolio_history.csv              # Daily portfolio snapshots
│   ├── positions_current.csv              # Open positions with P&L
│   └── performance_daily.csv              # Daily returns & cumulative metrics
└── logs/
    └── trading_log_YYYY-MM-DD.txt         # Daily activity logs & debug info
```

### Key Benefits of This Structure

**For Development:**
- **Incremental**: Each phase adds to the structure without breaking previous work
- **Testable**: Every JSON file has a corresponding CSV for manual verification
- **Debuggable**: Clear separation between raw data (JSON) and human views (CSV)

**For Daily Use:**
- **Quick Analysis**: Open `data/exports/` folder in Excel to see everything
- **Performance Tracking**: `portfolio_history.csv` shows your strategy performance over time
- **Trade Review**: `trades_summary.csv` shows all your paper trades with P&L
- **Signal Verification**: `signals_current.csv` shows what your strategy is thinking

**For Trading System:**
- **Structured Data**: All JSON files are easy for Python to read/write
- **Market Focus**: `filtered_markets.json` gives you individual markets to trade (not just events)
- **State Management**: `portfolio.json` tracks your current positions and balance
- **Historical Data**: Daily snapshots for backtesting and analysis