```sql
SELECT *
FROM public.events
WHERE title ILIKE '%Gaza%' OR title ILIKE '%gaza%' 
ORDER BY volume DESC;

SELECT *
FROM public.events
WHERE title ILIKE '%Gaza%' OR title ILIKE '%gaza%' 
ORDER BY volume DESC;

-- Truncate all data from tables defined in the multi-portfolio schema, preserving structures and respecting foreign key constraints.
-- Use CASCADE where required to avoid constraint errors.
-- NOTE: The order is chosen to satisfy foreign key relationships. 
-- WARNING: This deletes ALL DATA in these tables.

TRUNCATE TABLE
    portfolio_history,
    portfolio_positions,
    trades,
    trading_signals,
    markets,
    events,
    market_snapshots,
    portfolios
RESTART IDENTITY CASCADE;

-- Also clear the schema_version table if you want a full reset:
-- TRUNCATE TABLE schema_version RESTART IDENTITY CASCADE;

```