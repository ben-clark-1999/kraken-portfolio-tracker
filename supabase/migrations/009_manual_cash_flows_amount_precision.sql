-- Fix amount_aud precision to match the codebase's AUD column convention
-- (other AUD columns use numeric(14,4); 008 incorrectly used numeric(20,8)
-- which is the crypto-quantity scale).
ALTER TABLE public.manual_cash_flows
  ALTER COLUMN amount_aud TYPE numeric(14,4);
