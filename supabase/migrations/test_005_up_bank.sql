-- Mirror of 005_up_bank.sql for the `test` schema. Test fixtures
-- truncate these tables between cases.

CREATE TABLE test.up_accounts (LIKE public.up_accounts INCLUDING ALL);
CREATE TABLE test.up_categories (LIKE public.up_categories INCLUDING ALL);
CREATE TABLE test.up_transactions (LIKE public.up_transactions INCLUDING ALL);
CREATE TABLE test.up_sync_log (LIKE public.up_sync_log INCLUDING ALL);

ALTER TABLE test.portfolio_snapshots
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'crypto'
  CHECK (source IN ('crypto', 'up'));
