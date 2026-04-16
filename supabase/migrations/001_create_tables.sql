CREATE TABLE lots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset TEXT NOT NULL,
  acquired_at TIMESTAMPTZ NOT NULL,
  quantity NUMERIC(20, 8) NOT NULL,
  cost_aud NUMERIC(20, 2) NOT NULL,
  cost_per_unit_aud NUMERIC(20, 2) NOT NULL,
  kraken_trade_id TEXT UNIQUE NOT NULL,
  remaining_quantity NUMERIC(20, 8) NOT NULL
);

CREATE TABLE portfolio_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  captured_at TIMESTAMPTZ NOT NULL,
  total_value_aud NUMERIC(20, 2) NOT NULL,
  assets JSONB NOT NULL
);

CREATE TABLE sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_trade_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('success', 'error')),
  error_message TEXT
);

CREATE TABLE prices (
  asset TEXT PRIMARY KEY,
  price_aud NUMERIC(20, 2) NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lots_asset ON lots(asset);
CREATE INDEX idx_lots_acquired_at ON lots(acquired_at DESC);
CREATE INDEX idx_snapshots_captured_at ON portfolio_snapshots(captured_at DESC);
