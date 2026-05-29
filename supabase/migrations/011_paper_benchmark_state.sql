-- 011_paper_benchmark_state.sql
-- Holds the benchmark experiment start (t0) and the t0 reference prices used
-- to compute buy-and-hold benchmark equity curves. See spec §3.4.

create table paper_benchmark_state (
  benchmark_key   text primary key,   -- e.g. 'experiment'
  t0              timestamptz not null,
  prices_jsonb    jsonb not null default '{}'::jsonb,   -- {"BTC/AUD": "...", "ETH/AUD": "...", ...}
  updated_at      timestamptz not null default now()
);
