-- Mirror of 006_paper_trading.sql for the `test` schema. Test fixtures
-- truncate these tables between cases. Enums declared in 006_paper_trading.sql
-- are global (not schema-scoped) and reused here. FKs from the public schema
-- are deliberately dropped (LIKE INCLUDING ALL does not copy them); test
-- fixtures manage referential integrity at insert order.

CREATE TABLE test.strategies (LIKE public.strategies INCLUDING ALL);
CREATE TABLE test.paper_orders (LIKE public.paper_orders INCLUDING ALL);
CREATE TABLE test.paper_fills (LIKE public.paper_fills INCLUDING ALL);
CREATE TABLE test.paper_positions (LIKE public.paper_positions INCLUDING ALL);
CREATE TABLE test.agent_decisions (LIKE public.agent_decisions INCLUDING ALL);
CREATE TABLE test.paper_equity_snapshots (LIKE public.paper_equity_snapshots INCLUDING ALL);
CREATE TABLE test.paper_benchmarks (LIKE public.paper_benchmarks INCLUDING ALL);
CREATE TABLE test.system_alerts (LIKE public.system_alerts INCLUDING ALL);
