-- Manual trades: buy/sell pairs detected on Kraken (spend+receive sharing
-- a refid). One row per Kraken trade, dedup'd by kraken_refid. Walked from
-- the same ledger fetch that populates manual_cash_flows so the leaderboard
-- never needs a live Kraken call at request time.
CREATE TABLE public.manual_trades (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  kraken_refid    text          NOT NULL UNIQUE,
  side            text          NOT NULL CHECK (side IN ('buy','sell')),
  base_asset      text          NOT NULL,
  base_qty        numeric(20,8) NOT NULL,
  aud_amount      numeric(14,4) NOT NULL,
  fee_aud         numeric(14,4) NOT NULL DEFAULT 0,
  occurred_at     timestamptz   NOT NULL,
  created_at      timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX idx_manual_trades_occurred_at
  ON public.manual_trades (occurred_at);
