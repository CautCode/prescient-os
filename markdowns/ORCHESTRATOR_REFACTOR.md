# Orchestrator Refactor - Strategy-Centric Architecture

## Executive Summary

This document outlines a comprehensive refactoring plan to move from a centralized filtering architecture to a **strategy-centric architecture** where each trading strategy controller owns its own filtering logic, market selection criteria, and signal generation. The orchestrator (currently `trading_controller.py`) will become a lightweight coordinator that simply triggers strategy-specific workflows without knowing the details of how each strategy operates.

**Key Changes:**
1. **Rename** `trading_controller.py` → `portfolio_orchestrator.py`
2. **Move filtering logic** from orchestrator → individual strategy controllers
3. **Create strategy-specific controllers** for each trading strategy (momentum, mean reversion, etc.)
4. **Simplify orchestrator** to pure coordination role
5. **Strategy controllers own** their filtering parameters, market selection, and signal generation

---

## Table of Contents

1. [Current Architecture Problems](#current-architecture-problems)
2. [Proposed Architecture](#proposed-architecture)
3. [Strategy Controller Design](#strategy-controller-design)
4. [Orchestrator Simplification](#orchestrator-simplification)
5. [File Structure Changes](#file-structure-changes)
6. [Code Changes by File](#code-changes-by-file)
7. [Migration Path](#migration-path)
8. [Benefits of New Architecture](#benefits-of-new-architecture)

---

## Current Architecture Problems

### Problem 1: Orchestrator Owns Filtering Logic

**Current Flow:**
```
Orchestrator (trading_controller.py)
  ↓
  Calls events_controller with filtering params
  ↓
  Calls market_controller with filtering params
  ↓
  Calls strategy_controller (no params, just generates signals)
  ↓
  Calls paper_trading_controller to execute
```

**Issues:**
- Orchestrator must know filtering parameters for all strategies
- Single set of filtering parameters applied to all portfolios
- Cannot have strategy-specific filtering logic
- Adding new strategies requires modifying orchestrator
- Filtering parameters are hardcoded in orchestrator endpoints
- Strategy controller is "dumb" - just receives filtered data

### Problem 2: Portfolio Strategy Mapping is Weak

**Current:**
- Portfolio has `strategy_type` field (e.g., "momentum")
- Portfolio has `strategy_config` JSONB field for parameters
- But orchestrator ignores these and applies same filters to all
- Strategy controller on port 8002 doesn't know which portfolio it's serving

**Issues:**
- Portfolio strategy configuration is unused
- Cannot run different strategies with different filtering criteria
- Strategy controller doesn't receive portfolio context

### Problem 3: Cannot Scale to Multiple Strategies

**Current:**
- Single `trading_strategy_controller.py` with hardcoded ">50% buy strategy"
- If we want multiple strategies (momentum, mean reversion, arbitrage), we'd need:
  - Multiple controller files or
  - Single controller with strategy routing logic
- But orchestrator still controls filtering, so strategies can't customize

**Issues:**
- Hard to add new strategies
- Strategies can't have unique filtering requirements
- Tight coupling between orchestrator and strategy logic

---

## Proposed Architecture

### New Flow (Strategy-Centric)

```
Portfolio Orchestrator (portfolio_orchestrator.py)
  ↓
  Gets portfolio configuration (strategy_type + strategy_config)
  ↓
  Maps to appropriate strategy controller based on strategy_type
  ↓
Strategy Controller (e.g., momentum_strategy_controller.py)
  ↓
  1. Reads portfolio strategy_config to get filtering parameters
  2. Calls events_controller with strategy-specific filters
  3. Calls market_controller with strategy-specific filters
  4. Analyzes filtered data with strategy-specific logic
  5. Generates signals specific to this strategy
  6. Returns signals to orchestrator
  ↓
Portfolio Orchestrator
  ↓
  Calls paper_trading_controller to execute signals for this portfolio
```

### Key Principles

1. **Strategy Controllers Own Everything**
   - Filtering parameters
   - Market selection criteria
   - Signal generation logic
   - Strategy-specific analysis

2. **Orchestrator is Lightweight**
   - Maps portfolios to strategy controllers
   - Coordinates workflow
   - Handles errors and retries
   - Creates snapshots
   - Does NOT know about filtering

3. **Portfolios Drive Strategy Behavior**
   - `strategy_type` maps to strategy controller
   - `strategy_config` contains all strategy parameters
   - Each portfolio can have unique configuration

4. **True Strategy Isolation**
   - Each strategy is independent
   - Strategies can be deployed separately
   - Adding new strategy = new controller file + update routing

---

## Strategy Controller Design

### Strategy Controller Interface

Each strategy controller should expose a unified interface:

```python
# Base interface for all strategy controllers

@app.post("/strategy/execute-full-cycle")
async def execute_full_strategy_cycle(portfolio_id: int):
    """
    Execute complete strategy cycle for a specific portfolio

    This endpoint handles:
    1. Reading portfolio strategy_config
    2. Filtering events with strategy-specific criteria
    3. Filtering markets with strategy-specific criteria
    4. Analyzing markets with strategy logic
    5. Generating trading signals

    Args:
        portfolio_id: Portfolio to execute strategy for

    Returns:
        Generated signals and execution details
    """
    pass

@app.get("/strategy/info")
async def get_strategy_info():
    """
    Get information about this strategy

    Returns:
        Strategy metadata (name, description, default config, etc.)
    """
    pass

@app.get("/strategy/validate-config")
async def validate_strategy_config(config: Dict):
    """
    Validate a strategy configuration

    Args:
        config: Strategy configuration to validate

    Returns:
        Validation result
    """
    pass
```

### Strategy Controller Implementation Pattern

**File: `src/strategies/momentum_strategy_controller.py`**

```python
# Momentum Strategy Controller
# Strategy: Buy markets with >50% probability on most likely outcome
# Filters: High liquidity, moderate conviction (0.5-0.6)

from fastapi import FastAPI, HTTPException
import requests
from src.db.operations import get_portfolio_state, insert_signals

app = FastAPI(title="Momentum Strategy Controller", version="1.0.0")

# Strategy metadata
STRATEGY_INFO = {
    "name": "Momentum Strategy",
    "description": "Buy markets with >50% probability on the most likely outcome",
    "strategy_type": "momentum",
    "default_config": {
        # Event filtering
        "event_min_liquidity": 50000,
        "event_min_volume": 100000,
        "event_min_volume_24hr": 10000,
        "event_max_days_until_end": 30,
        "event_min_days_until_end": 1,

        # Market filtering
        "market_min_liquidity": 10000,
        "market_min_volume": 50000,
        "market_min_volume_24hr": 5000,
        "market_min_conviction": 0.50,
        "market_max_conviction": 0.65,

        # Strategy-specific
        "min_confidence": 0.75,
        "max_positions": 10,
        "trade_amount": 100
    }
}

@app.post("/strategy/execute-full-cycle")
async def execute_full_strategy_cycle(portfolio_id: int):
    """
    Execute complete momentum strategy cycle for a portfolio
    """
    try:
        logger.info(f"=== MOMENTUM STRATEGY: Starting cycle for portfolio {portfolio_id} ===")

        # Step 1: Load portfolio and get strategy config
        portfolio = get_portfolio_state(portfolio_id)
        strategy_config = {**STRATEGY_INFO["default_config"], **portfolio.get('strategy_config', {})}

        logger.info(f"Portfolio: {portfolio['name']}")
        logger.info(f"Strategy config: {strategy_config}")

        # Step 2: Filter events with strategy-specific criteria
        logger.info("Step 1: Filtering events with momentum strategy criteria...")
        events_response = requests.get(
            "http://localhost:8000/events/export-all-active-events-db"
        )
        events_response.raise_for_status()

        filter_events_response = requests.get(
            f"http://localhost:8000/events/filter-trading-candidates-db",
            params={
                "min_liquidity": strategy_config["event_min_liquidity"],
                "min_volume": strategy_config["event_min_volume"],
                "min_volume_24hr": strategy_config["event_min_volume_24hr"],
                "max_days_until_end": strategy_config["event_max_days_until_end"],
                "min_days_until_end": strategy_config["event_min_days_until_end"]
            }
        )
        filter_events_response.raise_for_status()

        events_result = filter_events_response.json()
        logger.info(f"✓ Filtered {events_result.get('total_candidates', 0)} events")

        # Step 3: Filter markets with strategy-specific criteria
        logger.info("Step 2: Filtering markets with momentum strategy criteria...")
        filter_markets_response = requests.get(
            f"http://localhost:8001/markets/export-filtered-markets-db",
            params={
                "min_liquidity": strategy_config["market_min_liquidity"],
                "min_volume": strategy_config["market_min_volume"],
                "min_volume_24hr": strategy_config["market_min_volume_24hr"],
                "min_market_conviction": strategy_config["market_min_conviction"],
                "max_market_conviction": strategy_config["market_max_conviction"]
            }
        )
        filter_markets_response.raise_for_status()

        markets_result = filter_markets_response.json()
        logger.info(f"✓ Filtered {markets_result.get('filtered_markets', 0)} markets")

        # Step 4: Load filtered markets from database
        from src.db.operations import get_markets
        markets_data = get_markets({'is_filtered': True})

        if not markets_data:
            logger.warning("No markets found after filtering")
            return {
                "message": "No markets available for momentum strategy",
                "portfolio_id": portfolio_id,
                "signals_generated": 0,
                "timestamp": datetime.now().isoformat()
            }

        # Step 5: Apply momentum strategy logic
        logger.info(f"Step 3: Analyzing {len(markets_data)} markets with momentum strategy...")
        signals = generate_momentum_signals(
            markets_data,
            min_confidence=strategy_config["min_confidence"],
            max_positions=strategy_config["max_positions"],
            trade_amount=strategy_config["trade_amount"]
        )

        logger.info(f"✓ Generated {len(signals)} signals")

        # Step 6: Save signals to database
        if signals:
            logger.info("Step 4: Saving signals to database...")
            prepared_signals = prepare_signals_for_db(signals)
            inserted_ids = insert_signals(prepared_signals, portfolio_id=portfolio_id, strategy_type="momentum")
            logger.info(f"✓ Saved {len(inserted_ids)} signals")

        logger.info(f"=== MOMENTUM STRATEGY: Completed cycle for portfolio {portfolio_id} ===")

        return {
            "message": "Momentum strategy cycle completed",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "strategy_type": "momentum",
            "signals_generated": len(signals),
            "markets_analyzed": len(markets_data),
            "strategy_config_used": strategy_config,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in momentum strategy cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def generate_momentum_signals(markets_data: List[Dict],
                               min_confidence: float,
                               max_positions: int,
                               trade_amount: float) -> List[Dict]:
    """
    Generate signals using momentum strategy logic (>50% buy most likely)
    """
    signals = []
    current_time = datetime.now()

    for market in markets_data:
        try:
            # Parse market data
            market_id = market.get('id')
            yes_price = float(market.get('yes_price', 0))
            no_price = float(market.get('no_price', 0))

            # Momentum strategy: Buy if either price > 50%
            if yes_price > 0.50 or no_price > 0.50:
                if yes_price >= no_price:
                    action = 'buy_yes'
                    target_price = yes_price
                    confidence = yes_price - 0.50
                    reason = f"Momentum: YES price {yes_price:.3f} > 0.50"
                else:
                    action = 'buy_no'
                    target_price = no_price
                    confidence = no_price - 0.50
                    reason = f"Momentum: NO price {no_price:.3f} > 0.50"

                # Check confidence threshold
                if confidence < (min_confidence - 0.50):
                    continue

                signal = {
                    'timestamp': current_time.isoformat(),
                    'market_id': market_id,
                    'market_question': market.get('question'),
                    'action': action,
                    'target_price': target_price,
                    'amount': trade_amount,
                    'confidence': round(confidence, 4),
                    'reason': reason,
                    'yes_price': yes_price,
                    'no_price': no_price,
                    'market_liquidity': float(market.get('liquidity', 0)),
                    'market_volume': float(market.get('volume', 0)),
                    'event_id': market.get('event_id'),
                    'event_title': market.get('event_title'),
                    'event_end_date': market.get('event_end_date')
                }

                signals.append(signal)

                # Limit positions
                if len(signals) >= max_positions:
                    break

        except Exception as e:
            logger.warning(f"Error processing market {market.get('id')}: {e}")
            continue

    # Sort by confidence
    signals.sort(key=lambda x: x['confidence'], reverse=True)

    return signals[:max_positions]


@app.get("/strategy/info")
async def get_strategy_info():
    """Get momentum strategy metadata"""
    return STRATEGY_INFO


@app.get("/strategy/validate-config")
async def validate_strategy_config(config: Dict):
    """Validate momentum strategy configuration"""
    required_fields = [
        "event_min_liquidity", "market_min_liquidity",
        "min_confidence", "trade_amount"
    ]

    missing = [f for f in required_fields if f not in config]

    if missing:
        return {
            "valid": False,
            "errors": [f"Missing required field: {f}" for f in missing]
        }

    return {"valid": True, "errors": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
```

### Additional Strategy Controllers

**File: `src/strategies/mean_reversion_strategy_controller.py`** (Port 8005)

```python
# Mean Reversion Strategy Controller
# Strategy: Buy markets that are highly imbalanced, betting on reversion to 50%
# Filters: High conviction (>0.7), high volume for liquidity

STRATEGY_INFO = {
    "name": "Mean Reversion Strategy",
    "description": "Buy markets that are highly imbalanced, betting on reversion",
    "strategy_type": "mean_reversion",
    "default_config": {
        # More aggressive filtering for volatile markets
        "event_min_liquidity": 100000,
        "event_min_volume": 200000,
        "event_min_volume_24hr": 20000,

        "market_min_liquidity": 50000,
        "market_min_volume": 100000,
        "market_min_conviction": 0.70,  # High conviction = imbalanced
        "market_max_conviction": 0.95,  # Not completely certain

        "min_confidence": 0.70,
        "max_positions": 5,
        "trade_amount": 200  # Higher risk, higher reward
    }
}

def generate_mean_reversion_signals(markets_data, ...):
    """
    Buy the UNDERDOG (less likely outcome) betting on reversion

    Strategy logic:
    - If yes_price > 0.70: BUY NO (bet against the favorite)
    - If no_price > 0.70: BUY YES (bet against the favorite)
    - Higher conviction = stronger reversion signal
    """
    # Implementation here
    pass
```

**File: `src/strategies/arbitrage_strategy_controller.py`** (Port 8006)

```python
# Arbitrage Strategy Controller
# Strategy: Find correlated markets with price discrepancies
# Filters: Very high liquidity, multiple markets per event

STRATEGY_INFO = {
    "name": "Arbitrage Strategy",
    "description": "Find correlated markets with price discrepancies",
    "strategy_type": "arbitrage",
    "default_config": {
        # Need high liquidity for entry/exit
        "event_min_liquidity": 500000,
        "event_min_volume": 1000000,

        "market_min_liquidity": 100000,
        "market_min_volume": 200000,
        # No conviction filter - we want all markets in an event

        "min_profit_margin": 0.05,  # 5% minimum profit
        "max_positions": 8,
        "trade_amount": 150
    }
}

def generate_arbitrage_signals(markets_data, ...):
    """
    Find arbitrage opportunities across correlated markets

    Strategy logic:
    - Group markets by event
    - Find correlated outcomes (e.g., "Will X win?" and "Will Y lose?")
    - Calculate if combined positions create risk-free profit
    - Execute paired trades
    """
    # Implementation here
    pass
```

---

## Orchestrator Simplification

### New Orchestrator (portfolio_orchestrator.py)

The orchestrator becomes much simpler - it just coordinates the workflow:

```python
# portfolio_orchestrator.py
# Lightweight orchestrator that coordinates portfolio trading cycles

from fastapi import FastAPI, HTTPException
import requests
from src.db.operations import get_portfolio_state, get_all_portfolios

app = FastAPI(title="Portfolio Orchestrator", version="1.0.0")

# Strategy controller mapping
STRATEGY_CONTROLLER_PORTS = {
    'momentum': 8002,
    'mean_reversion': 8005,
    'arbitrage': 8006,
    'hybrid': 8007
}

def get_strategy_controller_url(strategy_type: str) -> str:
    """Map strategy type to controller URL"""
    port = STRATEGY_CONTROLLER_PORTS.get(strategy_type)
    if not port:
        raise ValueError(f"Unknown strategy type: {strategy_type}")
    return f"http://localhost:{port}"


@app.post("/orchestrator/run-portfolio-cycle")
async def run_portfolio_cycle(portfolio_id: int):
    """
    Run complete trading cycle for a single portfolio

    Simple workflow:
    1. Get portfolio info (strategy_type)
    2. Call appropriate strategy controller
    3. Execute signals via paper trading controller
    4. Create portfolio snapshot
    """
    try:
        logger.info(f"=== ORCHESTRATOR: Starting cycle for portfolio {portfolio_id} ===")

        # Step 1: Get portfolio
        portfolio = get_portfolio_state(portfolio_id)
        strategy_type = portfolio['strategy_type']

        logger.info(f"Portfolio: {portfolio['name']} | Strategy: {strategy_type}")

        # Step 2: Get strategy controller URL
        strategy_url = get_strategy_controller_url(strategy_type)

        # Step 3: Call strategy controller to execute full cycle
        # The strategy controller handles ALL filtering and signal generation
        logger.info(f"Calling {strategy_type} strategy controller...")
        strategy_response = requests.post(
            f"{strategy_url}/strategy/execute-full-cycle",
            params={"portfolio_id": portfolio_id},
            timeout=300
        )
        strategy_response.raise_for_status()
        strategy_result = strategy_response.json()

        logger.info(f"✓ Strategy generated {strategy_result.get('signals_generated', 0)} signals")

        # Step 4: Execute signals
        logger.info("Executing signals...")
        execute_response = requests.get(
            f"http://localhost:8003/paper-trading/execute-signals",
            params={"portfolio_id": portfolio_id},
            timeout=300
        )
        execute_response.raise_for_status()
        execute_result = execute_response.json()

        logger.info(f"✓ Executed {execute_result.get('execution_summary', {}).get('executed_trades', 0)} trades")

        # Step 5: Update prices
        logger.info("Updating prices...")
        price_response = requests.get(
            f"http://localhost:8003/price-updater/update",
            params={"portfolio_id": portfolio_id}
        )
        # Don't fail if price update fails

        # Step 6: Create snapshot
        logger.info("Creating portfolio snapshot...")
        portfolio_response = requests.get(
            f"http://localhost:8003/portfolios/{portfolio_id}"
        )
        portfolio_response.raise_for_status()

        portfolio_data = portfolio_response.json().get('portfolio', {})
        snapshot_data = {
            'balance': portfolio_data.get('current_balance', 0),
            'positions': portfolio_data.get('positions', []),
            'total_invested': portfolio_data.get('total_invested', 0),
            'total_profit_loss': portfolio_data.get('total_profit_loss', 0),
            'trade_count': portfolio_data.get('trade_count', 0)
        }

        from src.trading_controller import create_daily_portfolio_snapshot
        create_daily_portfolio_snapshot(snapshot_data, portfolio_id=portfolio_id)

        logger.info(f"=== ORCHESTRATOR: Completed cycle for portfolio {portfolio_id} ===")

        return {
            "message": f"Portfolio cycle completed for {portfolio['name']}",
            "portfolio_id": portfolio_id,
            "portfolio_name": portfolio['name'],
            "strategy_type": strategy_type,
            "strategy_result": strategy_result,
            "execution_result": execute_result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in portfolio cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/orchestrator/run-all-portfolios")
async def run_all_portfolios():
    """
    Run trading cycle for all active portfolios

    Simple workflow:
    1. Get all active portfolios
    2. For each portfolio, call run_portfolio_cycle
    3. Aggregate results
    """
    try:
        logger.info("=== ORCHESTRATOR: Starting cycle for all active portfolios ===")

        portfolios = get_all_portfolios(status='active')
        logger.info(f"Found {len(portfolios)} active portfolios")

        if not portfolios:
            raise HTTPException(status_code=404, detail="No active portfolios found")

        results = []

        for portfolio in portfolios:
            try:
                # Call run_portfolio_cycle for each portfolio
                result = await run_portfolio_cycle(portfolio['portfolio_id'])
                results.append({
                    "portfolio_id": portfolio['portfolio_id'],
                    "status": "success",
                    "result": result
                })
            except Exception as portfolio_error:
                logger.error(f"Error in portfolio {portfolio['portfolio_id']}: {portfolio_error}")
                results.append({
                    "portfolio_id": portfolio['portfolio_id'],
                    "status": "error",
                    "error": str(portfolio_error)
                })

        successful = len([r for r in results if r['status'] == 'success'])
        failed = len([r for r in results if r['status'] == 'error'])

        logger.info(f"=== ORCHESTRATOR: Completed all portfolios ({successful} success, {failed} failed) ===")

        return {
            "message": f"Completed cycles for {len(portfolios)} portfolios",
            "summary": {
                "total_portfolios": len(portfolios),
                "successful": successful,
                "failed": failed
            },
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in run_all_portfolios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orchestrator/status")
async def get_orchestrator_status():
    """Get status of all strategy controllers and system health"""
    status = {
        "timestamp": datetime.now().isoformat(),
        "strategy_controllers": {}
    }

    for strategy_type, port in STRATEGY_CONTROLLER_PORTS.items():
        try:
            url = f"http://localhost:{port}/strategy/info"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            status["strategy_controllers"][strategy_type] = {
                "status": "online",
                "port": port,
                "info": response.json()
            }
        except Exception as e:
            status["strategy_controllers"][strategy_type] = {
                "status": "offline",
                "port": port,
                "error": str(e)
            }

    return status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
```

### Key Simplifications

**Before (trading_controller.py):**
- 980 lines of code
- Knows about event filtering parameters
- Knows about market filtering parameters
- Hardcoded filtering logic in endpoints
- Complex parameter passing

**After (portfolio_orchestrator.py):**
- ~200 lines of code
- No knowledge of filtering parameters
- Just maps portfolio → strategy controller
- Strategy controller does the heavy lifting
- Clean separation of concerns

---

## File Structure Changes

### Current Structure

```
src/
├── trading_controller.py           # 980 lines - orchestrator + filtering
├── trading_strategy_controller.py  # 328 lines - single strategy
├── paper_trading_controller.py     # 1032 lines - execution
├── events_controller.py            # Event filtering
├── market_controller.py            # Market filtering
└── db/
    └── operations.py
```

### Proposed Structure

```
src/
├── portfolio_orchestrator.py       # 200 lines - pure orchestration (renamed from trading_controller.py)
├── paper_trading_controller.py     # 1032 lines - execution (unchanged)
├── events_controller.py            # Event filtering (unchanged)
├── market_controller.py            # Market filtering (unchanged)
├── strategies/                     # NEW: Strategy controllers directory
│   ├── __init__.py
│   ├── base_strategy.py           # Base class/interface for strategies
│   ├── momentum_strategy_controller.py      # Port 8002
│   ├── mean_reversion_strategy_controller.py # Port 8005
│   ├── arbitrage_strategy_controller.py      # Port 8006
│   └── hybrid_strategy_controller.py         # Port 8007
└── db/
    └── operations.py               # Add strategy-specific operations if needed
```

---

## Code Changes by File

### 1. Rename and Simplify: `trading_controller.py` → `portfolio_orchestrator.py`

**Changes:**
- Remove all filtering parameter handling from endpoints
- Remove direct calls to events_controller and market_controller
- Simplify `run_portfolio_cycle` to just call strategy controller
- Simplify `run_all_portfolios` to iterate and call run_portfolio_cycle
- Add strategy controller mapping logic
- Remove `run_full_trading_cycle` endpoint (deprecated - use portfolio-specific cycles)

**Functions to Remove:**
- All filtering parameter logic in endpoints
- Direct filtering API calls

**Functions to Keep:**
- `run_portfolio_cycle` (simplified)
- `run_all_portfolios` (simplified)
- `get_trading_status` (updated to check strategy controllers)
- `get_performance_summary` (unchanged)
- `create_daily_portfolio_snapshot` (unchanged)

**Functions to Add:**
- `get_strategy_controller_url(strategy_type)`
- `validate_strategy_controller_online(strategy_type)`

### 2. Refactor: `trading_strategy_controller.py` → `strategies/momentum_strategy_controller.py`

**Changes:**
- Move file to `src/strategies/` directory
- Add portfolio_id parameter to generate_signals endpoint
- Add new `/strategy/execute-full-cycle` endpoint that handles:
  - Loading portfolio strategy_config
  - Calling events_controller with strategy-specific filters
  - Calling market_controller with strategy-specific filters
  - Generating signals
  - Saving signals to database
- Add `/strategy/info` endpoint for metadata
- Add `/strategy/validate-config` endpoint
- Update `generate_momentum_signals()` to accept config parameters

**New Endpoints:**
```python
POST /strategy/execute-full-cycle?portfolio_id={id}
GET  /strategy/info
POST /strategy/validate-config
```

**Deprecated Endpoints:**
```python
GET /strategy/generate-signals  # Now part of execute-full-cycle
```

### 3. Update: `paper_trading_controller.py`

**Changes:**
- No major changes needed!
- Already supports portfolio_id parameter
- Already has portfolio management endpoints
- Just ensure all endpoints accept portfolio_id

**Verify:**
- `POST /paper-trading/execute-signals?portfolio_id={id}` ✓
- `GET /portfolios/{portfolio_id}` ✓
- `POST /portfolios/create` ✓
- `GET /portfolios/list` ✓

### 4. No Changes: `events_controller.py` and `market_controller.py`

**Why no changes?**
- These controllers are already designed to accept filtering parameters
- They're stateless utilities that just filter data
- Strategy controllers will call them with appropriate parameters

**Current API (already correct):**
```python
# Events Controller
GET /events/export-all-active-events-db
GET /events/filter-trading-candidates-db?min_liquidity=X&min_volume=Y&...

# Market Controller
GET /markets/export-filtered-markets-db?min_liquidity=X&min_volume=Y&...
```

### 5. Update: `src/db/operations.py`

**Changes:**
- Add `strategy_type` parameter to `insert_signals()` function
- Ensure signals table has proper portfolio_id and strategy_type linkage

**Modified Functions:**
```python
def insert_signals(signals: List[Dict], portfolio_id: int, strategy_type: str) -> List[int]:
    """
    Insert signals with portfolio and strategy context

    Args:
        signals: List of signal dictionaries
        portfolio_id: Target portfolio
        strategy_type: Strategy that generated signals

    Returns:
        List of inserted signal IDs
    """
    # Implementation
    pass
```

### 6. New: `src/strategies/base_strategy.py`

**Purpose:**
- Define base class/interface for all strategies
- Provide common utilities
- Enforce consistent API

```python
# Base Strategy Interface

from abc import ABC, abstractmethod
from typing import Dict, List
import requests

class BaseStrategyController(ABC):
    """
    Base class for all trading strategy controllers
    Defines the interface and common utilities
    """

    def __init__(self):
        self.events_api_base = "http://localhost:8000"
        self.markets_api_base = "http://localhost:8001"

    @abstractmethod
    def get_strategy_info(self) -> Dict:
        """Return strategy metadata"""
        pass

    @abstractmethod
    def generate_signals(self, markets_data: List[Dict], config: Dict) -> List[Dict]:
        """Generate signals using strategy logic"""
        pass

    def filter_events(self, config: Dict) -> Dict:
        """
        Filter events using strategy config
        Common utility used by all strategies
        """
        response = requests.get(
            f"{self.events_api_base}/events/filter-trading-candidates-db",
            params=self._extract_event_filters(config)
        )
        response.raise_for_status()
        return response.json()

    def filter_markets(self, config: Dict) -> Dict:
        """
        Filter markets using strategy config
        Common utility used by all strategies
        """
        response = requests.get(
            f"{self.markets_api_base}/markets/export-filtered-markets-db",
            params=self._extract_market_filters(config)
        )
        response.raise_for_status()
        return response.json()

    def _extract_event_filters(self, config: Dict) -> Dict:
        """Extract event filtering parameters from config"""
        return {
            "min_liquidity": config.get("event_min_liquidity"),
            "min_volume": config.get("event_min_volume"),
            "min_volume_24hr": config.get("event_min_volume_24hr"),
            "max_days_until_end": config.get("event_max_days_until_end"),
            "min_days_until_end": config.get("event_min_days_until_end")
        }

    def _extract_market_filters(self, config: Dict) -> Dict:
        """Extract market filtering parameters from config"""
        return {
            "min_liquidity": config.get("market_min_liquidity"),
            "min_volume": config.get("market_min_volume"),
            "min_volume_24hr": config.get("market_min_volume_24hr"),
            "min_market_conviction": config.get("market_min_conviction"),
            "max_market_conviction": config.get("market_max_conviction")
        }
```

---

## Migration Path

### Phase 1: Create New Strategy Structure (Week 1)

**Step 1.1: Create strategies directory**
```bash
mkdir src/strategies
touch src/strategies/__init__.py
```

**Step 1.2: Create base_strategy.py**
- Implement base class with common utilities
- Test that it can call events/markets controllers

**Step 1.3: Migrate existing strategy to momentum_strategy_controller.py**
- Copy `trading_strategy_controller.py` → `src/strategies/momentum_strategy_controller.py`
- Refactor to use base class
- Add `/strategy/execute-full-cycle` endpoint
- Add filtering logic
- Test independently on port 8002

**Step 1.4: Update database operations**
- Add `strategy_type` parameter to `insert_signals()`
- Test signal insertion with portfolio_id and strategy_type

### Phase 2: Create New Orchestrator (Week 2)

**Step 2.1: Create portfolio_orchestrator.py**
- Copy `trading_controller.py` → `portfolio_orchestrator.py`
- Remove all filtering logic
- Implement simplified `run_portfolio_cycle`
- Add strategy controller mapping
- Keep on same port (8004) for now

**Step 2.2: Test new orchestrator with momentum strategy**
- Create test portfolio with strategy_type='momentum'
- Run `POST /orchestrator/run-portfolio-cycle?portfolio_id={id}`
- Verify full cycle works
- Verify signals are generated with correct portfolio_id

**Step 2.3: Deprecate old endpoints**
- Add deprecation warnings to old `trading_controller.py` endpoints
- Update documentation

### Phase 3: Add Additional Strategies (Week 3+)

**Step 3.1: Create mean_reversion_strategy_controller.py**
- Implement mean reversion logic
- Deploy on port 8005
- Test independently

**Step 3.2: Create arbitrage_strategy_controller.py**
- Implement arbitrage logic
- Deploy on port 8006
- Test independently

**Step 3.3: Update orchestrator mapping**
- Add new strategy types to `STRATEGY_CONTROLLER_PORTS`
- Test with portfolios using new strategies

### Phase 4: Cleanup (Week 4)

**Step 4.1: Remove old trading_controller.py**
- Verify all systems use new portfolio_orchestrator.py
- Delete old file
- Update all documentation

**Step 4.2: Remove old trading_strategy_controller.py**
- Verify all portfolios use new strategy controllers
- Delete old file
- Update all documentation

**Step 4.3: Update deployment scripts**
- Update startup scripts to launch all strategy controllers
- Update port configuration
- Update health checks

---

## Benefits of New Architecture

### 1. True Strategy Isolation

**Before:**
- Single strategy controller
- Cannot customize filtering per strategy
- Hard to add new strategies

**After:**
- Each strategy is independent
- Strategies define their own filtering
- Adding new strategy = new file + update mapping

### 2. Portfolio-Strategy Binding

**Before:**
- Portfolio has unused `strategy_config` field
- All portfolios use same filtering
- Strategy doesn't know which portfolio it serves

**After:**
- Portfolio `strategy_config` drives strategy behavior
- Each portfolio can have unique configuration
- Strategy receives portfolio context

### 3. Simplified Orchestrator

**Before:**
- 980 lines of complex orchestration + filtering logic
- Hardcoded filtering parameters
- Tight coupling to strategy details

**After:**
- 200 lines of simple coordination
- No knowledge of filtering
- Loose coupling via strategy controller API

### 4. Better Scalability

**Before:**
- Adding strategy requires modifying orchestrator
- Cannot scale strategies independently
- Shared filtering bottleneck

**After:**
- Adding strategy = deploy new controller
- Each strategy can scale independently
- No shared bottlenecks

### 5. Easier Testing

**Before:**
- Must test entire orchestration flow
- Hard to test strategy in isolation
- Filtering and strategy logic mixed

**After:**
- Test strategies independently
- Mock strategy controllers in orchestrator tests
- Clear separation of concerns

### 6. Configuration Flexibility

**Before:**
```python
# In orchestrator endpoint - hardcoded
event_min_liquidity: float = 10000
event_min_volume: float = 50000
# ... many parameters
```

**After:**
```python
# In portfolio database
{
    "strategy_type": "momentum",
    "strategy_config": {
        "event_min_liquidity": 50000,
        "market_min_conviction": 0.55,
        "max_positions": 8
    }
}
```

### 7. Strategy Comparison

**Before:**
- Hard to run multiple strategies side-by-side
- Cannot A/B test strategies
- Single strategy at a time

**After:**
- Create multiple portfolios with different strategies
- Compare performance across strategies
- Run all strategies in parallel

---

## Example Usage Scenarios

### Scenario 1: Create Portfolio with Custom Strategy Config

```bash
# Create momentum portfolio with aggressive settings
curl -X POST http://localhost:8003/portfolios/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Aggressive Momentum",
    "description": "High risk momentum trading",
    "strategy_type": "momentum",
    "initial_balance": 50000,
    "strategy_config": {
        "event_min_liquidity": 100000,
        "event_min_volume": 200000,
        "market_min_conviction": 0.60,
        "market_max_conviction": 0.75,
        "min_confidence": 0.80,
        "max_positions": 5,
        "trade_amount": 500
    }
}'
```

### Scenario 2: Run Trading Cycle for Specific Portfolio

```bash
# Orchestrator automatically routes to correct strategy controller
curl -X POST http://localhost:8004/orchestrator/run-portfolio-cycle?portfolio_id=1
```

**What happens:**
1. Orchestrator gets portfolio (ID=1)
2. Sees strategy_type="momentum"
3. Calls `http://localhost:8002/strategy/execute-full-cycle?portfolio_id=1`
4. Momentum controller:
   - Reads portfolio strategy_config
   - Filters events with config params
   - Filters markets with config params
   - Generates momentum signals
   - Saves signals to database
5. Orchestrator executes signals via paper trading controller
6. Orchestrator creates portfolio snapshot

### Scenario 3: Run All Portfolios (Mixed Strategies)

```bash
# Run all active portfolios - each uses its own strategy
curl -X POST http://localhost:8004/orchestrator/run-all-portfolios
```

**What happens:**
- Portfolio 1 (momentum) → Routes to port 8002
- Portfolio 2 (mean_reversion) → Routes to port 8005
- Portfolio 3 (arbitrage) → Routes to port 8006
- Each strategy uses its own filtering and logic
- All execute independently and in parallel

### Scenario 4: Check Strategy Controller Status

```bash
# See which strategies are available
curl http://localhost:8004/orchestrator/status

# Response:
{
    "timestamp": "2025-01-12T10:00:00",
    "strategy_controllers": {
        "momentum": {
            "status": "online",
            "port": 8002,
            "info": {
                "name": "Momentum Strategy",
                "description": "Buy markets with >50% probability"
            }
        },
        "mean_reversion": {
            "status": "online",
            "port": 8005,
            "info": {...}
        },
        "arbitrage": {
            "status": "offline",
            "port": 8006,
            "error": "Connection refused"
        }
    }
}
```

### Scenario 5: Add New Strategy

```bash
# 1. Create new strategy controller file
# src/strategies/scalping_strategy_controller.py

# 2. Implement strategy interface
# - execute_full_cycle endpoint
# - strategy_info endpoint
# - Signal generation logic with custom filtering

# 3. Deploy on new port (e.g., 8008)

# 4. Update orchestrator mapping
# Add to STRATEGY_CONTROLLER_PORTS:
# 'scalping': 8008

# 5. Create portfolio with new strategy
curl -X POST http://localhost:8003/portfolios/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Scalping Portfolio",
    "strategy_type": "scalping",
    "initial_balance": 10000,
    "strategy_config": {
        "event_min_volume_24hr": 50000,
        "market_min_volume_24hr": 10000,
        "trade_frequency": "high",
        "profit_target": 0.02
    }
}'

# 6. Run cycle - orchestrator automatically routes to new controller
curl -X POST http://localhost:8004/orchestrator/run-portfolio-cycle?portfolio_id=4
```

---

## Deployment Considerations

### Port Allocation

```
8000: Events Controller (unchanged)
8001: Markets Controller (unchanged)
8002: Momentum Strategy Controller (moved from trading_strategy_controller)
8003: Paper Trading Controller (unchanged)
8004: Portfolio Orchestrator (renamed from trading_controller)
8005: Mean Reversion Strategy Controller (new)
8006: Arbitrage Strategy Controller (new)
8007: Hybrid Strategy Controller (new)
8008+: Future strategy controllers
```

### Startup Order

```bash
# 1. Start data/utility controllers
python -m src.events_controller &      # Port 8000
python -m src.market_controller &      # Port 8001
python -m src.paper_trading_controller & # Port 8003

# 2. Start strategy controllers
python -m src.strategies.momentum_strategy_controller &  # Port 8002
python -m src.strategies.mean_reversion_strategy_controller & # Port 8005
python -m src.strategies.arbitrage_strategy_controller & # Port 8006

# 3. Start orchestrator (depends on all above)
python -m src.portfolio_orchestrator & # Port 8004
```

### Health Checks

```bash
# Check all components
curl http://localhost:8004/orchestrator/status

# Check specific strategy
curl http://localhost:8002/strategy/info
```

---

## Summary

This refactoring transforms Prescient OS from a **monolithic, centralized architecture** to a **modular, strategy-centric architecture**.

**Key Transformations:**

| Aspect | Before | After |
|--------|--------|-------|
| **Filtering Logic** | Orchestrator owns | Strategy controllers own |
| **Strategy Config** | Ignored/unused | Drives strategy behavior |
| **Adding Strategies** | Modify orchestrator | New controller file only |
| **Portfolio-Strategy** | Weak coupling | Strong binding |
| **Orchestrator Role** | Heavy coordinator | Lightweight router |
| **Code Complexity** | 980 lines | 200 lines |
| **Scalability** | Limited | Independent scaling |

**Implementation Timeline:**
- Week 1: Create strategy infrastructure
- Week 2: Refactor orchestrator
- Week 3+: Add new strategies
- Week 4: Cleanup and deploy

**Benefits:**
- ✅ True strategy isolation
- ✅ Portfolio-driven configuration
- ✅ Simplified orchestration
- ✅ Easy to add new strategies
- ✅ Better testing
- ✅ Independent scaling
- ✅ Parallel strategy execution

This architecture supports the long-term vision of running multiple portfolios with diverse strategies, each optimized for different market conditions and risk profiles.
