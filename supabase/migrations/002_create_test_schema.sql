CREATE SCHEMA IF NOT EXISTS test;

CREATE TABLE test.lots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset TEXT NOT NULL,
  acquired_at TIMESTAMPTZ NOT NULL,
  quantity NUMERIC(20, 8) NOT NULL,
  cost_aud NUMERIC(20, 8) NOT NULL,
  cost_per_unit_aud NUMERIC(20, 8) NOT NULL,
  kraken_trade_id TEXT UNIQUE NOT NULL,
  remaining_quantity NUMERIC(20, 8) NOT NULL
);

CREATE TABLE test.portfolio_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  captured_at TIMESTAMPTZ NOT NULL,
  total_value_aud NUMERIC(20, 2) NOT NULL,
  assets JSONB NOT NULL
);

CREATE TABLE test.sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_trade_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('success', 'error')),
  error_message TEXT
);

CREATE TABLE test.prices (
  asset TEXT PRIMARY KEY,
  price_aud NUMERIC(20, 2) NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
