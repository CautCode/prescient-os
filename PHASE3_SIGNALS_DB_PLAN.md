# PostgreSQL Migration Plan - Phase 3: Trading Signals (DB-Only Writes)

**Created:** 2025-10-28
**Status:** Planning Phase
**Approach:** Trading Signals write directly to PostgreSQL (no JSON writes)
**Scope:** Strategy controller + signal consumers; no dual-write helpers

---

## Table of Contents

1. Overview
2. Pre-Migration Checklist
3. Phase 3 Scope
4. Database Operations Layer (Signals)
5. Implementation Steps
6. Testing Strategy
7. Rollback Plan
8. Success Criteria

---

## Overview

### Current State
- Signals generated in `src/trading_strategy_controller.py`.
- Historically saved to JSON (e.g., `data/trades/current_signals.json`) and archived monthly.

### Target State (Phase 3)
- Signals persist only to PostgreSQL table `trading_signals` (see `src/db/schema.sql`).
- Remove/disable JSON writes entirely for signals.
- Reads in updated paths come from DB operations.
- Execution linkage: signals marked executed and linked to `trades.trade_id`.

### Key Decisions
- ✅ No dual-write; DB-only writes for signals.
- ✅ Keep other controllers unchanged unless they consume current signals.
- ✅ Add a minimal signal operations section to `src/db/operations.py`.
- ✅ Update strategy controller to use DB ops for create/read/mark-executed.

---

## Pre-Migration Checklist

### Infrastructure Ready ✅
- [x] PostgreSQL 16 running; DB `prescient_os` exists.
- [x] `prescient_user` has required privileges.
- [x] Schema applied; `trading_signals` table present per `postgresql.md`.
- [x] Python deps installed: `psycopg2-binary`, `sqlalchemy`.
- [x] `src/db/connection.py` connectivity passes.

### Before Starting
- [ ] Confirm there are no remaining code paths writing signals to JSON.
- [ ] Optionally archive any legacy JSON files for reference; they will not be written again.

---

## Phase 3 Scope

### Included
- ✅ `src/trading_strategy_controller.py` signal persistence: DB-only writes.
- ✅ DB operations for signals in `src/db/operations.py` (insert, bulk insert, query, mark executed).
- ✅ Any API/view that exposes current signals should read from DB ops.

### Not Included (Future)
- ❌ Events/markets migration (Phase 4).
- ❌ Price updater changes.
- ❌ Global removal of JSON reads outside signals (later phases).

### Rationale for DB-Only
1. Signals are transient; JSON duplicates add little value.
2. DB enables lineage (signal → trade) and analytics.
3. Avoids dual-write inconsistency and reduces complexity.

---

## Database Operations Layer (Signals)

Add a new section to `src/db/operations.py`:

- insert_signal(signal: Dict): Insert a single signal.
- insert_signals(signals: List[Dict]): Bulk insert signals in one transaction.
- get_current_signals(limit: Optional[int] = None, executed: Optional[bool] = None) -> List[Dict]: Query signals.
- mark_signal_executed(signal_id: int, trade_id: str, executed_at: Optional[datetime] = None): Set executed=true and link to trade.

Notes:
- Use `from sqlalchemy import text` and `get_db()` from `src/db/connection.py`.
- Ensure all numeric fields are cast on read to native Python floats where applicable.
- Order results by `timestamp DESC`.

---

## Implementation Steps

### Step 1: Add Signal DB Operations
- Create the four functions above in `src/db/operations.py` under a new "SIGNAL OPERATIONS" section.

Verification:
```bash
python -c "from src.db.operations import insert_signal, get_current_signals; \
from datetime import datetime; \
insert_signal({
  'timestamp': datetime.now(), 'market_id': 'm1', 'market_question': 'Q?', 'action': 'buy_yes',
  'target_price': 0.55, 'amount': 100.0, 'confidence': 0.8, 'reason': 'test',
  'yes_price': 0.54, 'no_price': 0.46, 'market_liquidity': 100000.0, 'market_volume': 25000.0,
  'event_id': 'e1', 'event_title': 'Event', 'event_end_date': datetime.now(),
  'executed': False, 'executed_at': None, 'trade_id': None
}); \
print(get_current_signals(limit=1))"
```

Expected: One signal record returned from DB.

### Step 2: Update Strategy Controller (DB-Only)
- Replace JSON writes in `src/trading_strategy_controller.py` with bulk DB insert:
  - `persist_generated_signals(signals)` → prepares records and calls `insert_signals(prepared)`.
- For reads, use `get_current_signals(limit, executed=False)`.
- After executing a signal as a trade, call `mark_signal_executed(signal_id, trade_id)`.
- Do not call any dual-write helpers.

### Step 3: Remove JSON Writes for Signals
- Remove/comment any code writing to `data/trades/current_signals.json` and monthly archives.

### Step 4: Optional API Adjustments
- If `/signals/current` or similar exists, switch to `get_current_signals()`.

---

## Testing Strategy

### Unit Tests (`tests/test_signal_operations.py`)
- Test single insert: `insert_signal()` then `get_current_signals(limit=1)`.
- Test bulk insert: `insert_signals()` with multiple entries, verify order and count.
- Test mark executed: insert → fetch id → `mark_signal_executed(id, 'trade_123')` → verify flags and `trade_id`.

Run:
```bash
pytest tests/test_signal_operations.py -v
```

### Integration Tests
1. Generate signals via strategy controller.
2. Verify signals appear in DB via API or direct ops.
3. Execute a signal → create a trade → mark signal executed with `trade_id`.
4. Verify DB reflects executed status and linkage.

### SQL Verification
```sql
SELECT COUNT(*) FROM trading_signals;
SELECT id, market_id, action, executed, trade_id
FROM trading_signals
ORDER BY timestamp DESC
LIMIT 10;
```

---

## Rollback Plan

- Revert `trading_strategy_controller.py` edits to previous behavior if needed.
- (Optional) temporarily re-enable JSON writers if absolutely necessary.
- Signals created during Phase 3 remain safely in the DB.

---

## Success Criteria

- ✅ Signals write only to PostgreSQL (no JSON writes occur).
- ✅ Strategy controller uses DB ops to persist and read signals.
- ✅ Executed signals are linked to trades via `trade_id`.
- ✅ Unit/integration tests pass; manual SQL checks match expectations.

---

## Summary

Phase 3 migrates trading signals to PostgreSQL with DB-only writes, removing JSON persistence. It introduces focused DB operations, updates the strategy controller to use them, and provides testing and rollback guidance aligned with the broader migration roadmap.
