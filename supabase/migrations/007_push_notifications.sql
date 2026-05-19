-- Phone push notifications: per-strategy opt-in flag and per-decision
-- idempotency timestamp.
ALTER TABLE public.strategies
  ADD COLUMN IF NOT EXISTS notify_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE public.agent_decisions
  ADD COLUMN IF NOT EXISTS notified_at timestamptz NULL;
