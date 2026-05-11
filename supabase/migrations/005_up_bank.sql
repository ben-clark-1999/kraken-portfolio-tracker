-- UP Bank tables and snapshot source-awareness.

CREATE TABLE up_accounts (
  id              TEXT PRIMARY KEY,
  display_name    TEXT NOT NULL,
  account_type    TEXT NOT NULL,
  ownership_type  TEXT NOT NULL,
  balance_value   NUMERIC(20, 2) NOT NULL,
  balance_currency TEXT NOT NULL DEFAULT 'AUD',
  created_at      TIMESTAMPTZ NOT NULL,
  last_synced_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE up_categories (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  parent_id   TEXT REFERENCES up_categories(id)
);

CREATE TABLE up_transactions (
  id                 TEXT PRIMARY KEY,
  account_id         TEXT NOT NULL REFERENCES up_accounts(id),
  status             TEXT NOT NULL,
  description        TEXT NOT NULL,
  message            TEXT,
  raw_text           TEXT,
  amount_value       NUMERIC(20, 2) NOT NULL,
  amount_currency    TEXT NOT NULL DEFAULT 'AUD',
  category_id        TEXT REFERENCES up_categories(id),
  parent_category_id TEXT REFERENCES up_categories(id),
  created_at         TIMESTAMPTZ NOT NULL,
  settled_at         TIMESTAMPTZ,
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_up_tx_created_at ON up_transactions(created_at DESC);
CREATE INDEX idx_up_tx_category   ON up_transactions(parent_category_id, created_at DESC);
CREATE INDEX idx_up_tx_account    ON up_transactions(account_id, created_at DESC);

CREATE TABLE up_sync_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_tx_at TIMESTAMPTZ,
  status          TEXT NOT NULL CHECK (status IN ('success', 'error', 'in_progress')),
  error_message   TEXT
);

ALTER TABLE portfolio_snapshots
  ADD COLUMN source TEXT NOT NULL DEFAULT 'crypto'
  CHECK (source IN ('crypto', 'up'));

CREATE INDEX idx_snapshots_source_captured
  ON portfolio_snapshots(source, captured_at DESC);
