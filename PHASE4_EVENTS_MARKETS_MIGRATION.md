# Phase 4: Events & Markets Migration Plan

**Created:** 2025-10-28
**Status:** Planning Phase
**Approach:** Start fresh with PostgreSQL (no JSON migration or dual-write)
**Scope:** Events controller and Markets controller only

---

## Table of Contents

1. [Overview](#overview)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [Phase 4 Scope](#phase-4-scope)
4. [Database Operations Layer](#database-operations-layer)
5. [Implementation Steps](#implementation-steps)
6. [Testing Strategy](#testing-strategy)
7. [Rollback Plan](#rollback-plan)
8. [Success Criteria](#success-criteria)

---

## Overview

### Current State
- Events data stored in `data/events/raw_events_backup.json` and `data/events/filtered_events.json`
- Markets data stored in `data/markets/filtered_markets.json`
- Events controller fetches and filters events from Polymarket API
- Markets controller extracts markets from events and fetches detailed market data

### Phase 4 Target State
- **Events and markets** stored in PostgreSQL
- **Events and markets controllers** use database operations
- **Start fresh** - No need to migrate existing JSON data
- Existing JSON files can be archived or ignored

### Key Decisions
✅ **Phase 4 only** - Focus on events_controller.py and market_controller.py
✅ **Start fresh in database** - No JSON-to-DB migration needed
✅ **No dual-write complexity** - Direct database operations only
✅ **Keep trading signals in JSON** - Trading strategy controller stays unchanged for now
✅ **Minimal operations layer** - Only events and markets operations

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
- [x] Phase 1 complete (Portfolio & Trades working)

### Before Starting Phase 4
- [ ] Verify database tables exist: `events`, `markets`, `market_snapshots`
- [ ] Archive existing JSON files (optional - can keep for reference)
- [ ] Understand that trading_strategy_controller still reads from JSON (will migrate later)

---

## Phase 4 Scope

### What's Included in Phase 4
✅ **Events Controller** (`src/events_controller.py`)
  - Fetch events from Polymarket API
  - Filter events for trading viability
  - Store in PostgreSQL instead of JSON

✅ **Markets Controller** (`src/market_controller.py`)
  - Extract markets from filtered events
  - Apply market trading filters
  - Fetch detailed market data from API
  - Store in PostgreSQL instead of JSON

✅ **Database Tables Used**
  - `events` - Filtered events with metadata
  - `markets` - Filtered markets with detailed data
  - `market_snapshots` - Time-series market price data

### What's NOT Included (Future Phases)
❌ Trading strategy controller - still reads `current_signals.json` for now
❌ Price updater - will be migrated later
❌ Historical data migration - starting fresh is fine

### Why Phase 4 Now?
1. **Events and markets are reference data** - Can start fresh without losing critical business data
2. **Trading signals depend on markets** - Need this before migrating trading_strategy_controller
3. **Enables time-series analysis** - Market snapshots will track price changes over time
4. **Clean slate** - No need to migrate old events/markets data

---

## Database Operations Layer

### Update `src/db/operations.py` - Add Events & Markets Functions

Add these functions to the existing `src/db/operations.py` file:

```python
import json

# ============================================================================
# EVENT OPERATIONS
# ============================================================================

def upsert_events(events: List[Dict]):
    """Insert or update events in database"""
    with get_db() as db:
        for event in events:
            db.execute(text("""
                INSERT INTO events
                (event_id, title, slug, liquidity, volume, volume24hr,
                 start_date, end_date, days_until_end, event_data, is_filtered, updated_at)
                VALUES (:event_id, :title, :slug, :liquidity, :volume, :volume24hr,
                        :start_date, :end_date, :days_until_end, :event_data::jsonb, :is_filtered, NOW())
                ON CONFLICT (event_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    slug = EXCLUDED.slug,
                    liquidity = EXCLUDED.liquidity,
                    volume = EXCLUDED.volume,
                    volume24hr = EXCLUDED.volume24hr,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    days_until_end = EXCLUDED.days_until_end,
                    event_data = EXCLUDED.event_data,
                    is_filtered = EXCLUDED.is_filtered,
                    updated_at = NOW()
            """), {
                'event_id': event.get('id'),
                'title': event.get('title'),
                'slug': event.get('slug'),
                'liquidity': event.get('liquidity', 0),
                'volume': event.get('volume', 0),
                'volume24hr': event.get('volume24hr', 0),
                'start_date': event.get('startDate'),
                'end_date': event.get('endDate'),
                'days_until_end': event.get('days_until_end'),
                'event_data': json.dumps(event),
                'is_filtered': event.get('is_filtered', False)
            })
        db.commit()


def get_events(filters: Dict = None) -> List[Dict]:
    """Get events with optional filters"""
    with get_db() as db:
        query = """
            SELECT event_id, title, slug, liquidity, volume, volume24hr,
                   start_date, end_date, days_until_end, event_data, is_filtered
            FROM events
        """

        params = {}
        where_clauses = []

        if filters:
            if 'is_filtered' in filters:
                where_clauses.append("is_filtered = :is_filtered")
                params['is_filtered'] = filters['is_filtered']

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY volume DESC"

        results = db.execute(text(query), params).fetchall()

        events = []
        for row in results:
            event_data = json.loads(row[9]) if row[9] else {}
            event_data.update({
                'id': row[0],
                'title': row[1],
                'slug': row[2],
                'liquidity': float(row[3]) if row[3] else 0.0,
                'volume': float(row[4]) if row[4] else 0.0,
                'volume24hr': float(row[5]) if row[5] else 0.0,
                'startDate': row[6],
                'endDate': row[7],
                'days_until_end': row[8],
                'is_filtered': row[10]
            })
            events.append(event_data)

        return events


def clear_filtered_events():
    """Clear all filtered events (useful before re-filtering)"""
    with get_db() as db:
        db.execute(text("UPDATE events SET is_filtered = FALSE WHERE is_filtered = TRUE"))
        db.commit()


# ============================================================================
# MARKET OPERATIONS
# ============================================================================

def upsert_markets(markets: List[Dict]):
    """Insert or update markets in database"""
    with get_db() as db:
        for market in markets:
            db.execute(text("""
                INSERT INTO markets
                (market_id, question, event_id, event_title, event_end_date,
                 liquidity, volume, volume24hr, yes_price, no_price, market_conviction,
                 market_data, is_filtered, updated_at)
                VALUES (:market_id, :question, :event_id, :event_title, :event_end_date,
                        :liquidity, :volume, :volume24hr, :yes_price, :no_price,
                        :market_conviction, :market_data::jsonb, :is_filtered, NOW())
                ON CONFLICT (market_id) DO UPDATE SET
                    question = EXCLUDED.question,
                    liquidity = EXCLUDED.liquidity,
                    volume = EXCLUDED.volume,
                    volume24hr = EXCLUDED.volume24hr,
                    yes_price = EXCLUDED.yes_price,
                    no_price = EXCLUDED.no_price,
                    market_conviction = EXCLUDED.market_conviction,
                    market_data = EXCLUDED.market_data,
                    is_filtered = EXCLUDED.is_filtered,
                    updated_at = NOW()
            """), {
                'market_id': market.get('id'),
                'question': market.get('question'),
                'event_id': market.get('event_id'),
                'event_title': market.get('event_title'),
                'event_end_date': market.get('event_end_date'),
                'liquidity': market.get('liquidity', 0),
                'volume': market.get('volume', 0),
                'volume24hr': market.get('volume24hr', 0),
                'yes_price': market.get('yes_price'),
                'no_price': market.get('no_price'),
                'market_conviction': market.get('market_conviction'),
                'market_data': json.dumps(market),
                'is_filtered': market.get('is_filtered', True)
            })
        db.commit()


def get_markets(filters: Dict = None) -> List[Dict]:
    """Get markets with optional filters"""
    with get_db() as db:
        query = """
            SELECT market_id, question, event_id, event_title, event_end_date,
                   liquidity, volume, volume24hr, yes_price, no_price,
                   market_conviction, market_data, is_filtered
            FROM markets
        """

        params = {}
        where_clauses = []

        if filters:
            if 'is_filtered' in filters:
                where_clauses.append("is_filtered = :is_filtered")
                params['is_filtered'] = filters['is_filtered']

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY volume DESC"

        results = db.execute(text(query), params).fetchall()

        markets = []
        for row in results:
            market_data = json.loads(row[11]) if row[11] else {}
            market_data.update({
                'id': row[0],
                'question': row[1],
                'event_id': row[2],
                'event_title': row[3],
                'event_end_date': row[4],
                'liquidity': float(row[5]) if row[5] else 0.0,
                'volume': float(row[6]) if row[6] else 0.0,
                'volume24hr': float(row[7]) if row[7] else 0.0,
                'yes_price': float(row[8]) if row[8] else None,
                'no_price': float(row[9]) if row[9] else None,
                'market_conviction': float(row[10]) if row[10] else None,
                'is_filtered': row[12]
            })
            markets.append(market_data)

        return markets


def insert_market_snapshot(market_id: str, prices: Dict):
    """Insert a market price snapshot for time-series tracking"""
    with get_db() as db:
        db.execute(text("""
            INSERT INTO market_snapshots
            (market_id, yes_price, no_price, liquidity, volume, volume24hr, market_conviction)
            VALUES (:market_id, :yes_price, :no_price, :liquidity, :volume, :volume24hr, :market_conviction)
        """), {
            'market_id': market_id,
            'yes_price': prices.get('yes_price'),
            'no_price': prices.get('no_price'),
            'liquidity': prices.get('liquidity'),
            'volume': prices.get('volume'),
            'volume24hr': prices.get('volume24hr'),
            'market_conviction': prices.get('market_conviction')
        })
        db.commit()


def clear_filtered_markets():
    """Clear all filtered markets (useful before re-filtering)"""
    with get_db() as db:
        db.execute(text("UPDATE markets SET is_filtered = FALSE WHERE is_filtered = TRUE"))
        db.commit()
```

---

## Implementation Steps

### Step 1: Update Database Operations File

Add the events and markets functions to `src/db/operations.py` (code provided above).

**Verification:**
```bash
python -c "from src.db.operations import upsert_events, get_events, upsert_markets, get_markets; print('Events & Markets operations loaded successfully!')"
```

### Step 2: Update Events Controller

Modify `src/events_controller.py`:

**Update `export_all_active_events_json()` endpoint:**

Replace the JSON file write with database write:

```python
@app.get("/events/export-all-active-events-json")
async def export_all_active_events_json():
    """
    Export all active events to database (no longer saves to JSON)

    Returns:
        JSON response with summary info
    """
    try:
        logger.info("Starting database export of all active events...")

        # Reuse the existing get_active_events logic
        active_events_response = await get_active_events()

        # Extract events from response
        all_events = active_events_response if isinstance(active_events_response, list) else active_events_response.get('data', active_events_response)

        logger.info(f"Retrieved {len(all_events)} events for database export")

        # Mark all as NOT filtered initially
        for event in all_events:
            event['is_filtered'] = False

        # Save to database
        from src.db.operations import upsert_events
        upsert_events(all_events)

        logger.info(f"Successfully exported {len(all_events)} events to database")

        return {
            "message": "All active events saved to database successfully",
            "total_events": len(all_events),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Unexpected error in export_all_active_events_json: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
```

**Update `filter_trading_candidates_json()` endpoint:**

Replace JSON read/write with database operations:

```python
@app.get("/events/filter-trading-candidates-json")
async def filter_trading_candidates_json(
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    max_days_until_end: int = 90,
    min_days_until_end: int = 1
):
    """
    Filter events from database to create trading candidates

    Args:
        min_liquidity: Minimum liquidity threshold
        min_volume: Minimum total volume threshold
        min_volume_24hr: Minimum 24hr volume threshold
        max_days_until_end: Maximum days until event ends
        min_days_until_end: Minimum days until event ends

    Returns:
        JSON response with filtered trading candidates summary
    """
    from src.db.operations import get_events, upsert_events, clear_filtered_events

    try:
        logger.info("=== STARTING TRADING CANDIDATES FILTERING (DATABASE version) ===")
        logger.info(f"Parameters: min_liquidity={min_liquidity}, min_volume={min_volume}, max_days={max_days_until_end}")

        # Step 1: Read all events from database
        logger.info("Step 1: Loading events from database...")
        events_data = get_events()

        if not events_data:
            raise HTTPException(status_code=500, detail="No events found in database. Please export events first.")

        logger.info(f"✓ Successfully loaded {len(events_data)} events from database")

        # Step 2: Apply filters (same logic as before)
        logger.info("Step 2: Applying trading filters...")
        filtered_events = apply_json_trading_filters(
            events_list=events_data,
            min_liquidity=min_liquidity,
            min_volume=min_volume,
            min_volume_24hr=min_volume_24hr,
            max_days_until_end=max_days_until_end,
            min_days_until_end=min_days_until_end
        )
        logger.info(f"✓ Successfully applied filters. Filtered events count: {len(filtered_events)}")

        # Step 3: Mark filtered events in database
        logger.info("Step 3: Marking filtered events in database...")

        # Clear previous filtered flags
        clear_filtered_events()

        # Mark new filtered events
        for event in filtered_events:
            event['is_filtered'] = True

        upsert_events(filtered_events)
        logger.info(f"✓ Successfully marked {len(filtered_events)} events as filtered in database")

        # Step 4: Calculate summary statistics
        logger.info("Step 4: Calculating summary statistics...")
        total_candidates = len(filtered_events)

        if total_candidates > 0:
            avg_liquidity = sum(float(event.get('liquidity', 0)) for event in filtered_events) / total_candidates
            avg_volume = sum(float(event.get('volume', 0)) for event in filtered_events) / total_candidates
            avg_days = sum(e.get('days_until_end', 0) or 0 for e in filtered_events if e.get('days_until_end')) / len([e for e in filtered_events if e.get('days_until_end')]) if any(e.get('days_until_end') for e in filtered_events) else 0
        else:
            avg_liquidity = avg_volume = avg_days = 0

        logger.info("=== TRADING CANDIDATES FILTERING (DATABASE) COMPLETED ===")

        return {
            "message": "Trading candidates filtered and saved to database successfully",
            "total_candidates": total_candidates,
            "total_original_events": len(events_data),
            "filters_applied": {
                "min_liquidity": min_liquidity,
                "min_volume": min_volume,
                "min_volume_24hr": min_volume_24hr,
                "max_days_until_end": max_days_until_end,
                "min_days_until_end": min_days_until_end
            },
            "summary_stats": {
                "avg_liquidity": round(avg_liquidity, 2) if avg_liquidity else None,
                "avg_volume": round(avg_volume, 2) if avg_volume else None,
                "avg_days_until_end": round(avg_days, 1) if avg_days else None
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR IN FILTER_TRADING_CANDIDATES ===")
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
```

**Add new endpoint to get current filtered events:**

```python
@app.get("/events/current-filtered")
async def get_current_filtered_events():
    """
    Get current filtered events from database

    Returns:
        Current filtered events
    """
    from src.db.operations import get_events

    try:
        events_data = get_events({'is_filtered': True})

        if not events_data:
            raise HTTPException(status_code=404, detail="No filtered events found. Please filter trading candidates first.")

        return {
            "message": "Current filtered events retrieved from database",
            "events_count": len(events_data),
            "events": events_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading filtered events: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading filtered events: {str(e)}")
```

### Step 3: Update Markets Controller

Modify `src/market_controller.py`:

**Update `export_filtered_markets_json()` endpoint:**

Replace JSON read/write with database operations:

```python
@app.get("/markets/export-filtered-markets-json")
async def export_filtered_markets_json(
    min_liquidity: float = 10000,
    min_volume: float = 50000,
    min_volume_24hr: Optional[float] = None,
    min_market_conviction: Optional[float] = None,
    max_market_conviction: Optional[float] = None
):
    """
    Export filtered markets to database (reads filtered events from database)

    Args:
        min_liquidity: Minimum liquidity threshold
        min_volume: Minimum total volume threshold
        min_volume_24hr: Minimum 24hr volume threshold
        min_market_conviction: Minimum market conviction threshold
        max_market_conviction: Maximum market conviction threshold

    Returns:
        JSON response with filtered market summary
    """
    from src.db.operations import get_events, upsert_markets, insert_market_snapshot, clear_filtered_markets

    try:
        logger.info("=== STARTING MARKET FILTERING (DATABASE version) ===")
        logger.info(f"Parameters: min_liquidity={min_liquidity}, min_volume={min_volume}")

        # Step 1: Read filtered events from database
        logger.info("Step 1: Loading filtered events from database...")
        events_data = get_events({'is_filtered': True})

        if not events_data:
            raise HTTPException(status_code=500, detail="No filtered events found in database. Please filter events first.")

        logger.info(f"✓ Successfully loaded {len(events_data)} filtered events from database")

        # Step 2: Extract markets from events (same as before)
        logger.info("Step 2: Extracting markets from events...")
        all_markets = extract_markets_from_events(events_data)

        if not all_markets:
            raise HTTPException(status_code=404, detail="No markets found in filtered events")

        # Step 3: Apply market filters (same as before)
        logger.info("Step 3: Applying market trading filters...")
        filtered_markets = apply_market_trading_filters(
            markets_list=all_markets,
            min_liquidity=min_liquidity,
            min_volume=min_volume,
            min_volume_24hr=min_volume_24hr,
            min_market_conviction=min_market_conviction,
            max_market_conviction=max_market_conviction
        )
        logger.info(f"✓ Successfully applied filters. Filtered markets count: {len(filtered_markets)}")

        # Step 4: Get market IDs for API fetching (same as before)
        logger.info("Step 4: Extracting market IDs for API fetching...")
        market_ids = extract_market_ids_from_filtered_markets(filtered_markets)

        if not market_ids:
            return {
                "message": "No markets passed the trading filters",
                "total_original_markets": len(all_markets),
                "filtered_markets": 0,
                "timestamp": datetime.now().isoformat()
            }

        # Step 5: Fetch detailed market data from API (same as before)
        logger.info("Step 5: Fetching detailed market data from API...")
        detailed_markets_data = fetch_all_markets_data(market_ids)

        if not detailed_markets_data:
            raise HTTPException(status_code=503, detail="Failed to fetch any detailed market data from API")

        # Step 6: Save to database instead of JSON
        logger.info("Step 6: Saving filtered markets to database...")

        # Clear previous filtered flags
        clear_filtered_markets()

        # Mark as filtered
        for market in detailed_markets_data:
            market['is_filtered'] = True

        upsert_markets(detailed_markets_data)

        # Also save market snapshots for price history
        for market in detailed_markets_data:
            insert_market_snapshot(market['id'], {
                'yes_price': market.get('yes_price'),
                'no_price': market.get('no_price'),
                'liquidity': market.get('liquidity'),
                'volume': market.get('volume'),
                'volume24hr': market.get('volume24hr'),
                'market_conviction': market.get('market_conviction')
            })

        logger.info(f"✓ Successfully saved {len(detailed_markets_data)} markets to database")

        # Step 7: Calculate summary statistics
        logger.info("Step 7: Calculating summary statistics...")
        total_filtered = len(detailed_markets_data)
        if total_filtered > 0:
            avg_liquidity = sum(float(m.get('liquidity', 0)) for m in detailed_markets_data) / total_filtered
            avg_volume = sum(float(m.get('volume', 0)) for m in detailed_markets_data) / total_filtered
        else:
            avg_liquidity = avg_volume = 0

        logger.info("=== MARKET FILTERING (DATABASE) COMPLETED ===")

        return {
            "message": "Market trading candidates filtered and saved to database successfully",
            "total_original_markets": len(all_markets),
            "filtered_markets": len(filtered_markets),
            "fetched_detailed_markets": len(detailed_markets_data),
            "filters_applied": {
                "min_liquidity": min_liquidity,
                "min_volume": min_volume,
                "min_volume_24hr": min_volume_24hr,
                "min_market_conviction": min_market_conviction,
                "max_market_conviction": max_market_conviction
            },
            "summary_stats": {
                "avg_liquidity": round(avg_liquidity, 2) if avg_liquidity else None,
                "avg_volume": round(avg_volume, 2) if avg_volume else None
            },
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== UNEXPECTED ERROR IN MARKET FILTERING ===")
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
```

**Update `get_current_filtered_markets()` endpoint:**

Replace JSON read with database read:

```python
@app.get("/markets/current-filtered")
async def get_current_filtered_markets():
    """
    Get current filtered markets from database

    Returns:
        Current filtered markets data
    """
    from src.db.operations import get_markets

    try:
        markets_data = get_markets({'is_filtered': True})

        if not markets_data:
            raise HTTPException(status_code=404, detail="Filtered markets not found. Please filter trading candidates first.")

        return {
            "message": "Current filtered markets retrieved from database",
            "markets_count": len(markets_data),
            "markets": markets_data,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading filtered markets: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading filtered markets: {str(e)}")
```

**Update `get_market_status()` endpoint:**

Update to check database:

```python
@app.get("/markets/status")
async def get_market_status():
    """
    Get status of market data system (database version)

    Returns:
        Status information about filtered markets
    """
    from src.db.operations import get_markets

    try:
        status = {
            "timestamp": datetime.now().isoformat(),
            "filtered_markets_exists": False,
            "filtered_markets_count": 0
        }

        # Check filtered markets in database
        try:
            markets_data = get_markets({'is_filtered': True})
            status["filtered_markets_exists"] = True
            status["filtered_markets_count"] = len(markets_data)
        except:
            pass

        return status

    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting market status: {str(e)}")
```

**Remove `ensure_data_directories()` function:**

No longer needed since we're not writing to JSON files.

### Step 4: Update Trading Strategy Controller (Minor Change)

The trading_strategy_controller.py still writes signals to JSON, but needs to read markets from database:

Modify `generate_signals()` in `src/trading_strategy_controller.py`:

```python
@app.get("/strategy/generate-signals")
async def generate_signals():
    """
    Generate trading signals based on filtered markets (reads from database)

    Returns:
        Generated signals and summary
    """
    from src.db.operations import get_markets

    try:
        logger.info("=== STARTING TRADING SIGNAL GENERATION ===")

        # Step 1: Read filtered markets from DATABASE (not JSON)
        logger.info("Step 1: Loading filtered markets from database...")
        markets_data = get_markets({'is_filtered': True})

        if not markets_data:
            raise HTTPException(status_code=404,
                detail="No markets data found in database. Please filter markets first.")

        logger.info(f"✓ Successfully loaded {len(markets_data)} markets from database")

        # Step 2: Generate trading signals (same as before)
        logger.info("Step 2: Generating trading signals...")
        signals = generate_trading_signals(markets_data)

        # Step 3: Save signals to JSON (for now - will migrate in next phase)
        logger.info("Step 3: Saving trading signals to JSON...")
        signals_path = os.path.join("data", "trades", "current_signals.json")
        with open(signals_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Successfully saved {len(signals)} signals to JSON")

        # Return response...
        return {
            "message": "Trading signals generated successfully",
            "signals_count": len(signals),
            "signals": signals,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating signals: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating signals: {str(e)}")
```

---

## Testing Strategy

### Unit Tests

Test the new database operations:

```bash
python -c "
from src.db.operations import upsert_events, get_events, upsert_markets, get_markets
from datetime import datetime

# Test event operations
test_event = {
    'id': 'test_event_001',
    'title': 'Test Event',
    'slug': 'test-event',
    'liquidity': 50000,
    'volume': 100000,
    'volume24hr': 5000,
    'startDate': datetime.now().isoformat(),
    'endDate': datetime.now().isoformat(),
    'days_until_end': 30,
    'is_filtered': True
}

upsert_events([test_event])
print('✓ Test event inserted')

events = get_events({'is_filtered': True})
print(f'✓ Retrieved {len(events)} filtered events')

# Test market operations
test_market = {
    'id': 'test_market_001',
    'question': 'Test market question?',
    'event_id': 'test_event_001',
    'event_title': 'Test Event',
    'liquidity': 25000,
    'volume': 50000,
    'yes_price': 0.55,
    'no_price': 0.45,
    'market_conviction': 0.10,
    'is_filtered': True
}

upsert_markets([test_market])
print('✓ Test market inserted')

markets = get_markets({'is_filtered': True})
print(f'✓ Retrieved {len(markets)} filtered markets')

print('All tests passed!')
"
```

### Integration Tests

Test the complete workflow:

1. **Test events export:**
   ```bash
   curl http://localhost:8000/events/export-all-active-events-json
   ```
   Expected: Events saved to database

2. **Test events filtering:**
   ```bash
   curl "http://localhost:8000/events/filter-trading-candidates-json?min_liquidity=10000&min_volume=50000"
   ```
   Expected: Filtered events marked in database

3. **Test markets filtering:**
   ```bash
   curl "http://localhost:8000/markets/export-filtered-markets-json?min_liquidity=10000&min_volume=50000"
   ```
   Expected: Markets saved to database with snapshots

4. **Test signal generation:**
   ```bash
   curl http://localhost:8000/strategy/generate-signals
   ```
   Expected: Signals generated from database markets

5. **Verify in PostgreSQL:**
   ```sql
   -- Check events
   SELECT COUNT(*) FROM events;
   SELECT COUNT(*) FROM events WHERE is_filtered = TRUE;

   -- Check markets
   SELECT COUNT(*) FROM markets;
   SELECT COUNT(*) FROM markets WHERE is_filtered = TRUE;

   -- Check market snapshots
   SELECT COUNT(*) FROM market_snapshots;
   ```

---

## Rollback Plan

### If Phase 4 Fails

**Option 1: Revert code changes**
```bash
# Restore original controllers
git checkout HEAD~1 src/events_controller.py
git checkout HEAD~1 src/market_controller.py
git checkout HEAD~1 src/trading_strategy_controller.py

# Restart services - will use JSON files again
```

**Option 2: Keep database but use JSON temporarily**
- Trading strategy controller can still read from JSON
- Re-run events and markets filtering to JSON
- No critical data loss - events/markets can be re-fetched from API

---

## Success Criteria

### Phase 4 Complete When:
- ✅ Events export to database successfully
- ✅ Events filtering works with database
- ✅ Markets export to database successfully
- ✅ Markets filtering works with database
- ✅ Market snapshots created for time-series tracking
- ✅ Trading signals can be generated from database markets
- ✅ No errors in logs
- ✅ Full pipeline works end-to-end (events → markets → signals)

### Verification Checklist:
- [ ] `upsert_events()` stores events in database
- [ ] `get_events()` retrieves filtered events
- [ ] `upsert_markets()` stores markets in database
- [ ] `get_markets()` retrieves filtered markets
- [ ] `insert_market_snapshot()` creates time-series data
- [ ] Events controller endpoints work with database
- [ ] Markets controller endpoints work with database
- [ ] Trading strategy controller reads from database
- [ ] PostgreSQL queries show correct data
- [ ] Full trading pipeline executes successfully

---

## Summary

**Estimated Time:** 3-4 hours

**Files to Modify:**
1. `src/db/operations.py` - Add 8 new functions (events & markets operations)
2. `src/events_controller.py` - Replace 2 endpoints to use database
3. `src/market_controller.py` - Replace 3 endpoints to use database
4. `src/trading_strategy_controller.py` - Minor change to read markets from database

**Risk Level:** Low
- ✅ Events and markets can be re-fetched from API anytime
- ✅ No critical business data at risk
- ✅ Easy rollback via git
- ✅ Fresh start - no data migration complexity
- ✅ Trading signals still work (still in JSON for now)

**Benefits:**
- ✅ Time-series market tracking via snapshots
- ✅ Queryable events and markets data
- ✅ Better performance for market lookups
- ✅ Foundation for advanced analytics

**Next Phase (Future):**
- Phase 5: Migrate trading signals to database
- Phase 6: Migrate price updater to database
- Phase 7: Remove all JSON dependencies

---

**Ready to implement?** Start with Step 1: Update `src/db/operations.py`
