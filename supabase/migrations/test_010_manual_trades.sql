-- Mirror of public.manual_trades in the test schema. See public migration
-- 010_manual_trades.sql for column-level docs.
CREATE TABLE test.manual_trades (LIKE public.manual_trades INCLUDING ALL);
