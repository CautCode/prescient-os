# PostgreSQL Migration Plan - Phase 2: Historical Data (DB-Only Writes)

**Created:** 2025-10-28  
**Status:** Ready for implementation  
**Approach:** Portfolio history snapshots and monthly signal archives persist directly to PostgreSQL (no JSON writes)

---

## Table of Contents

1. Overview
2. Pre-Migration Checklist
3. Phase 2 Scope
4. Database Operations Layer (History)
5. Implementation Steps
6. Testing Strategy
7. Rollback Plan
8. Success Criteria

---

## Overview

### Current State
- Daily portfolio snapshots are appended to `data/history/portfolio_history.json`.
- Monthly signal archives are appended to `data/history/signals_archive_YYYY-MM.json` by `archive_current_signals()` reading from `data/trades/current_signals.json`.

### Target State (Phase 2)
- Portfolio snapshots persist only to PostgreSQL table `portfolio_history`.
- Signal archives persist only to PostgreSQL table `signal_archives`.
- No JSON writes for these two paths. Reads may still source existing JSON for inputs where appropriate until Phase 5.

### Key Decisions
- ✅ No dual-write; DB-only writes for history tables.
- ✅ Keep all other controllers unchanged.
- ✅ Extend `src/db/operations.py` with history operations.
- ✅ Update `src/trading_controller.py` to call DB operations for history persistence.

---

## Pre-Migration Checklist

### Infrastructure Ready ✅
- [x] PostgreSQL 16 running; DB `prescient_os` exists.
- [x] `prescient_user` has required privileges.
- [x] Schema applied; tables `portfolio_history` and `signal_archives` present per `src/db/schema.sql` (see `postgresql.md`).
- [x] Python deps installed: `psycopg2-binary`, `sqlalchemy`.
- [x] `src/db/connection.py` connectivity passes.

### Before Starting
- [ ] Confirm no external job still appends to `data/history/portfolio_history.json` or `data/history/signals_archive_*.json`.
- [ ] Optionally archive legacy JSON files for reference; they will not be written again.

---

## Phase 2 Scope

### Included
- ✅ `src/trading_controller.py` persistence for:
  - `create_daily_portfolio_snapshot(portfolio_data)` → insert into `portfolio_history` (DB-only).
  - `archive_current_signals()` → insert into `signal_archives` (DB-only), sourcing current signals from existing JSON file or API output as input data, but not writing JSON archives anymore.
- ✅ DB operations for history in `src/db/operations.py`.

### Not Included (Future Phases)
- ❌ Trading signals generation/storage changes (Phase 3).
- ❌ Markets/events migration (Phase 4).
- ❌ Global switch of reads to DB (Phase 5).

### Rationale for DB-Only
1. Historical data benefits most from indexed, queryable storage.
2. Eliminates file contention and simplifies retention.
3. Avoids dual-write inconsistency.

---

## Database Operations Layer (History)

Add a new section to `src/db/operations.py`:

- `insert_portfolio_history_snapshot(snapshot: Dict) -> int`  
  Inserts one row into `portfolio_history` and returns its `id`.

- `get_portfolio_history(limit: Optional[int] = None) -> List[Dict]`  
  Returns recent rows ordered by `snapshot_date DESC, timestamp DESC`.

- `insert_signal_archive(archived_at: datetime, signals: List[Dict]) -> int`  
  Computes `archive_month` as `YYYY-MM`, sets `signals_count`, stores `signals` as JSONB into `signal_archives`, returns `id`.

- `get_recent_signal_archives(limit: Optional[int] = None) -> List[Dict]`  
  Returns recent archives ordered by `archived_at DESC`.

Notes:
- Use `from sqlalchemy import text` and `get_db()` from `src/db/connection.py`.
- Cast numerics to native Python floats on read where applicable.
- Keep transactions small and explicit; commit after inserts.

---

## Implementation Steps

### Step 1: Add History DB Operations (in `src/db/operations.py`)
Append at the end of the file a new section:

- `insert_portfolio_history_snapshot(snapshot: Dict) -> int` inserting the following fields:
  - `snapshot_date`, `timestamp`, `balance`, `total_invested`, `total_profit_loss`, `total_value`, `open_positions`, `trade_count`.
- `get_portfolio_history(limit: Optional[int] = None) -> List[Dict]` ordered by `snapshot_date DESC, timestamp DESC` with numeric casts.
- `insert_signal_archive(archived_at: datetime, signals: List[Dict]) -> int` computing `archive_month = archived_at.strftime('%Y-%m')`, `signals_count = len(signals)`, `signals_data = json.dumps(signals)` stored as JSONB (use `CAST(:signals_data AS jsonb)`).
- `get_recent_signal_archives(limit: Optional[int] = None) -> List[Dict]` ordered by `archived_at DESC`.

Verification (ad-hoc):
```bash
python - <<"PY"
from datetime import datetime, date
from src.db.operations import insert_portfolio_history_snapshot, get_portfolio_history, insert_signal_archive, get_recent_signal_archives

snap_id = insert_portfolio_history_snapshot({
  'snapshot_date': date.today(),
  'timestamp': datetime.now(),
  'balance': 10000.0,
  'total_invested': 0.0,
  'total_profit_loss': 0.0,
  'total_value': 10000.0,
  'open_positions': 0,
  'trade_count': 0,
})
print('snapshot_id', snap_id)
print('history_top1', get_portfolio_history(limit=1))

arch_id = insert_signal_archive(datetime.now(), [{'market_id': 'm1', 'action': 'buy_yes'}])
print('archive_id', arch_id)
print('archives_top1', get_recent_signal_archives(limit=1))
PY
```

### Step 2: Update `src/trading_controller.py` (DB-only writes)

- `create_daily_portfolio_snapshot(portfolio_data: Dict)`
  - Remove JSON file read/append/write logic entirely.
  - Prepare snapshot dict and call `insert_portfolio_history_snapshot(snapshot)`.
  - Log the inserted `id` and summary; do not write to `data/history/portfolio_history.json`.

- `archive_current_signals()`
  - Stop writing monthly JSON archive files.
  - Source of signals for Phase 2 remains the current JSON file `data/trades/current_signals.json` (read-only) or, if available, an API response containing the current signals. The function will:
    - Read current signals (if file exists and non-empty), else return early.
    - Call `insert_signal_archive(archived_at=datetime.now(), signals=signals)`.
    - Log archive `id` and count; do not write to `data/history/signals_archive_*.json`.

- No changes to API routes are strictly required; only internal behavior of these two functions changes to DB-only writes.

### Step 3: Optional API Endpoints (read-only)
- Optionally expose read endpoints to verify history data:
  - `GET /trading/portfolio-history?limit=N` → uses `get_portfolio_history(limit)`.
  - `GET /trading/signal-archives?limit=N` → uses `get_recent_signal_archives(limit)`.

---

## Testing Strategy

### Unit Tests (`tests/test_history_operations.py`)
- Test portfolio snapshot insert and read-back ordering.
- Test signal archive insert with a sample signals array and read-back.

Run:
```bash
pytest tests/test_history_operations.py -v
```

### Integration Tests
1. Run a full trading cycle to produce a portfolio state.
2. Verify `create_daily_portfolio_snapshot()` creates a row in `portfolio_history`.
3. Place a few signals (from existing JSON or API), run `archive_current_signals()`.
4. Verify a new row in `signal_archives` with correct `signals_count` and JSONB content.

### SQL Verification
```sql
SELECT COUNT(*) FROM portfolio_history;
SELECT snapshot_date, balance, total_value
FROM portfolio_history
ORDER BY snapshot_date DESC, timestamp DESC
LIMIT 5;

SELECT archived_at, archive_month, signals_count
FROM signal_archives
ORDER BY archived_at DESC
LIMIT 5;
```

---

## Rollback Plan
- Revert `src/trading_controller.py` to previous JSON write logic for the two functions if needed.
- History rows created during Phase 2 remain safely in the DB.

---

## Success Criteria
- ✅ `create_daily_portfolio_snapshot()` writes only to `portfolio_history` (no JSON file writes).
- ✅ `archive_current_signals()` writes only to `signal_archives` (no monthly JSON archive writes).
- ✅ History reads via optional endpoints or ops return expected data with correct ordering.
- ✅ Manual SQL checks confirm inserted rows and accurate counts.

---

## Summary

Phase 2 migrates historical persistence (daily portfolio snapshots and monthly signal archives) to PostgreSQL with DB-only writes. It introduces focused DB operations and updates two functions in `src/trading_controller.py`, delivering queryable history while avoiding dual-write complexity.
