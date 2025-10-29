```sql
SELECT *
FROM public.events
WHERE title ILIKE '%Gaza%' OR title ILIKE '%gaza%' 
ORDER BY volume DESC;

SELECT *
FROM public.events
WHERE title ILIKE '%Gaza%' OR title ILIKE '%gaza%' 
ORDER BY volume DESC;

TRUNCATE TABLE public.events;
-- Delete all data from tables while keeping table structures
-- Delete in correct order to respect foreign key constraints

DELETE FROM trading_signals;
DELETE FROM signal_archives;
DELETE FROM market_snapshots;
DELETE FROM markets;
DELETE FROM events;
DELETE FROM portfolio_snapshots;
DELETE FROM portfolio_positions;
DELETE FROM portfolio_history;
DELETE FROM portfolio_state;
DELETE FROM system_metadata;
DELETE FROM trades;
```