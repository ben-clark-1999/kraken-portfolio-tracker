-- Mirror of 007_push_notifications.sql for the `test` schema.
-- `test.strategies` and `test.agent_decisions` were created with
-- CREATE TABLE ... (LIKE public.<x> INCLUDING ALL) in earlier migrations,
-- which does NOT auto-propagate later ALTERs. Apply the same changes.
ALTER TABLE test.strategies
  ADD COLUMN IF NOT EXISTS notify_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE test.agent_decisions
  ADD COLUMN IF NOT EXISTS notified_at timestamptz NULL;
