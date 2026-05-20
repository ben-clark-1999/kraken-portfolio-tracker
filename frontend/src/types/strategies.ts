export type ExecutionMode = 'llm_agent' | 'deterministic'
export type StrategyStatus = 'active' | 'paused' | 'archived'

export interface Strategy {
  id: string
  name: string
  description: string | null
  execution_mode: ExecutionMode
  persona_key: string | null
  deterministic_config: {
    cadence_cron: string
    tz: string
    allocations: Record<string, string>
  } | null
  starting_balance_aud: string
  trigger_config: Record<string, unknown>
  risk_caps: Record<string, unknown>
  kill_criteria: Record<string, unknown>
  model_preference: string | null
  status: StrategyStatus
  dry_run: boolean
  persona_prompt_stable_since: string | null
  created_at: string
  updated_at: string
}

export interface LeaderboardRow {
  id: string
  name: string
  status: StrategyStatus
  execution_mode: ExecutionMode
  equity_aud: string
  return_7d_pct: string
  return_30d_pct: string
  return_all_time_pct: string
  lifetime_return_pct: string
  sharpe: string
  max_drawdown_pct: string
  trades: number
  cost_30d_aud: string
  persona_prompt_stable_since: string | null
}

export interface EquityPoint {
  ts: string
  equity_aud: string
  cash_aud?: string
  position_value_aud?: string
}

export interface BenchmarkPoint {
  ts: string
  equity_aud: string
}

export interface EquityCurveResponse {
  strategy: EquityPoint[]
  benchmarks: {
    btc_hodl: BenchmarkPoint[]
    alt_basket_equal_weight: BenchmarkPoint[]
  }
}

export interface AgentDecision {
  id: string
  strategy_id: string
  execution_mode: string
  trigger_event: { type: string; [k: string]: unknown }
  input_snapshot: Record<string, unknown>
  persona_prompt_hash: string | null
  model: string | null
  input_tokens: number
  output_tokens: number
  cost_aud: string
  tool_calls: Array<{ tool: string; args?: Record<string, unknown> }>
  agent_output: string | null
  latency_ms: number | null
  error: string | null
  created_at: string
}

export interface OpenOrder {
  id: string
  strategy_id: string
  pair: string
  side: 'buy' | 'sell'
  type: 'market' | 'limit'
  qty: string
  limit_price: string | null
  expires_at: string | null
  status: string
  reject_reason: string | null
  created_at: string
}

export interface HealthResponse {
  ws_feed: Record<string, { last_tick_at: string | null; age_s: number | null }>
  strategies: Array<{ id: string; name: string; status: StrategyStatus }>
  executor: { last_fill_at: string | null; open_orders: number }
  db: { write_latency_ms_p99: number }
}

export type EquityRange = '1d' | '7d' | '30d' | '90d' | 'all'
