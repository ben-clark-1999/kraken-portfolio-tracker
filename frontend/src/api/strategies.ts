import { apiFetch } from './client'
import type {
  AgentDecision,
  EquityCurveResponse,
  EquityRange,
  HealthResponse,
  LeaderboardRow,
  OpenOrder,
  Strategy,
} from '../types/strategies'

const BASE = '/api/strategies'

async function getJson<T>(path: string): Promise<T> {
  const r = await apiFetch(path)
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json() as Promise<T>
}

async function postJson<T>(path: string): Promise<T> {
  const r = await apiFetch(path, { method: 'POST' })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json() as Promise<T>
}

export const fetchStrategies = () => getJson<Strategy[]>(`${BASE}/`)
export const fetchStrategy = (id: string) => getJson<Strategy>(`${BASE}/${id}`)
export const fetchLeaderboard = () => getJson<LeaderboardRow[]>(`${BASE}/_leaderboard`)
export const fetchHealth = () => getJson<HealthResponse>(`${BASE}/_health`)

export const fetchEquityCurve = (id: string, range: EquityRange = '30d') =>
  getJson<EquityCurveResponse>(`${BASE}/${id}/equity?range=${range}`)

export const fetchDecisions = (id: string, n = 20) =>
  getJson<AgentDecision[]>(`${BASE}/${id}/decisions?n=${n}`)

export const fetchOpenOrders = (id: string) =>
  getJson<OpenOrder[]>(`${BASE}/${id}/open_orders`)

export const fetchPositions = (id: string) =>
  getJson<Record<string, { qty: string; avg_cost_aud: string }>>(
    `${BASE}/${id}/positions`,
  )

export const pauseStrategy = (id: string) =>
  postJson<{ ok: boolean }>(`${BASE}/${id}/pause`)

export const resumeStrategy = (id: string) =>
  postJson<{ ok: boolean }>(`${BASE}/${id}/resume`)

export const archiveStrategy = (id: string) =>
  postJson<{ ok: boolean }>(`${BASE}/${id}/archive`)
