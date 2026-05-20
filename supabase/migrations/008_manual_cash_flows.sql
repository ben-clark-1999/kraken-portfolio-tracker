-- Manual portfolio cash flows: deposit/withdrawal events detected on Kraken.
-- One row per Kraken ledger entry, dedup'd by kraken_refid.
CREATE TABLE public.manual_cash_flows (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  kraken_refid    text          NOT NULL UNIQUE,
  kind            text          NOT NULL CHECK (kind IN ('deposit', 'withdrawal')),
  amount_aud      numeric(20,8) NOT NULL,
  occurred_at     timestamptz   NOT NULL,
  created_at      timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX idx_manual_cash_flows_occurred_at
  ON public.manual_cash_flows (occurred_at);
