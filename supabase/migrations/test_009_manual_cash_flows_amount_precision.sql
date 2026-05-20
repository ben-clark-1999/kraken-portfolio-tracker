-- Mirror of 009 for the test schema.
ALTER TABLE test.manual_cash_flows
  ALTER COLUMN amount_aud TYPE numeric(14,4);
