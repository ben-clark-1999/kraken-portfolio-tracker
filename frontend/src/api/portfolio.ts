import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import { apiFetch } from './client'

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await apiFetch(url)
  if (!res.ok) throw new Error(`${url} returned ${res.status} ${res.statusText}`)
  return res.json() as T
}

export async function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  return fetchJSON<PortfolioSummary>('/api/portfolio/summary')
}

export async function fetchSnapshots(from?: string, to?: string): Promise<PortfolioSnapshot[]> {
  const params = new URLSearchParams()
  if (from) params.set('from_dt', from)
  if (to) params.set('to_dt', to)
  const qs = params.size ? `?${params.toString()}` : ''
  return fetchJSON<PortfolioSnapshot[]>(`/api/history/snapshots${qs}`)
}

export async function fetchDCAHistory(): Promise<DCAEntry[]> {
  return fetchJSON<DCAEntry[]>('/api/history/trades')
}
