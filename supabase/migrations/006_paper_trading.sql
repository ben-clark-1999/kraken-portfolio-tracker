-- 006_paper_trading.sql
-- Paper-trading sandbox schema. See spec §4.

create type strategy_execution_mode as enum ('llm_agent', 'deterministic');
create type strategy_status         as enum ('active', 'paused', 'archived');
create type paper_order_side        as enum ('buy', 'sell');
create type paper_order_type        as enum ('market', 'limit');
create type paper_order_status      as enum ('pending', 'filled', 'partial', 'rejected', 'cancelled', 'expired');
create type paper_fee_role          as enum ('maker', 'taker');
create type system_alert_level      as enum ('info', 'warning', 'error');

create table strategies (
  id                            uuid primary key default gen_random_uuid(),
  name                          text not null,
  description                   text,
  execution_mode                strategy_execution_mode not null,
  persona_key                   text,
  deterministic_config          jsonb,
  starting_balance_aud          numeric(12,2) not null default 1000.00,
  trigger_config                jsonb not null default '{}'::jsonb,
  risk_caps                     jsonb not null default '{}'::jsonb,
  kill_criteria                 jsonb not null default '{}'::jsonb,
  model_preference              text,
  status                        strategy_status not null default 'active',
  dry_run                       boolean not null default false,
  persona_prompt_stable_since   timestamptz,
  created_at                    timestamptz not null default now(),
  updated_at                    timestamptz not null default now(),
  constraint persona_required_for_llm
    check (execution_mode = 'deterministic' or persona_key is not null),
  constraint deterministic_config_required_for_deterministic
    check (execution_mode = 'llm_agent' or deterministic_config is not null)
);

create table paper_orders (
  id                uuid primary key default gen_random_uuid(),
  strategy_id       uuid not null references strategies(id) on delete cascade,
  idempotency_key   text not null,
  pair              text not null,
  side              paper_order_side not null,
  type              paper_order_type not null,
  qty               numeric(20,10) not null,
  limit_price       numeric(20,10),
  expires_at        timestamptz,
  status            paper_order_status not null default 'pending',
  reject_reason     text,
  decided_by        uuid,
  created_at        timestamptz not null default now(),
  unique (strategy_id, idempotency_key)
);
create index paper_orders_strategy_status_idx on paper_orders (strategy_id, status);
create index paper_orders_created_idx on paper_orders (strategy_id, created_at desc);

create table paper_fills (
  id                uuid primary key default gen_random_uuid(),
  order_id          uuid not null references paper_orders(id) on delete cascade,
  qty               numeric(20,10) not null,
  price             numeric(20,10) not null,
  fee_aud           numeric(12,4) not null default 0,
  fee_role          paper_fee_role not null,
  book_state_hash   text,
  filled_at         timestamptz not null default now()
);
create index paper_fills_order_idx on paper_fills (order_id);

create table paper_positions (
  strategy_id       uuid not null references strategies(id) on delete cascade,
  asset             text not null,
  qty               numeric(20,10) not null default 0,
  avg_cost_aud      numeric(12,4) not null default 0,
  lots_jsonb        jsonb not null default '[]'::jsonb,
  updated_at        timestamptz not null default now(),
  primary key (strategy_id, asset)
);

create table agent_decisions (
  id                    uuid primary key default gen_random_uuid(),
  strategy_id           uuid not null references strategies(id) on delete cascade,
  execution_mode        strategy_execution_mode not null,
  trigger_event         jsonb not null,
  input_snapshot        jsonb not null,
  persona_prompt_hash   text,
  model                 text,
  input_tokens          integer not null default 0,
  output_tokens         integer not null default 0,
  cost_aud              numeric(10,4) not null default 0,
  tool_calls            jsonb not null default '[]'::jsonb,
  agent_output          text,
  latency_ms            integer,
  error                 text,
  created_at            timestamptz not null default now()
);
create index agent_decisions_strategy_created_idx
  on agent_decisions (strategy_id, created_at desc);

-- Now that agent_decisions exists, link paper_orders.decided_by to it.
alter table paper_orders
  add constraint paper_orders_decided_by_fk
  foreign key (decided_by) references agent_decisions(id) on delete set null;

create table paper_equity_snapshots (
  strategy_id           uuid not null references strategies(id) on delete cascade,
  ts                    timestamptz not null,
  equity_aud            numeric(14,4) not null,
  cash_aud              numeric(14,4) not null,
  position_value_aud    numeric(14,4) not null,
  realised_pnl_aud      numeric(14,4) not null default 0,
  unrealised_pnl_aud    numeric(14,4) not null default 0,
  primary key (strategy_id, ts)
);

create table paper_benchmarks (
  benchmark_key         text not null,
  ts                    timestamptz not null,
  equity_aud            numeric(14,4) not null,
  primary key (benchmark_key, ts)
);

create table system_alerts (
  id                    uuid primary key default gen_random_uuid(),
  level                 system_alert_level not null,
  code                  text not null,
  strategy_id           uuid references strategies(id) on delete set null,
  message               text not null,
  payload               jsonb not null default '{}'::jsonb,
  acknowledged_at       timestamptz,
  created_at            timestamptz not null default now()
);
create index system_alerts_unack_idx
  on system_alerts (created_at desc) where acknowledged_at is null;

-- View: per-strategy LLM cost roll-up (referenced in spec §7.4).
create view paper_strategy_costs as
  select strategy_id,
         date_trunc('day', created_at) as day,
         sum(cost_aud)::numeric(12,4) as cost_aud,
         count(*) as invocations
  from agent_decisions
  where execution_mode = 'llm_agent'
  group by 1, 2;
