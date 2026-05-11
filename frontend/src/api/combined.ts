import { apiFetch } from './client'
import type { CombinedSnapshot, CombinedSummary } from '../types/up'

export async function fetchCombinedSnapshots(since?: string): Promise<CombinedSnapshot[]> {
  const url = since
    ? `/api/combined/snapshots?since=${encodeURIComponent(since)}`
    : '/api/combined/snapshots'
  const r = await apiFetch(url)
  if (!r.ok) throw new Error(`combined snapshots: ${r.status}`)
  return r.json()
}

export async function fetchCombinedSummary(): Promise<CombinedSummary> {
  const r = await apiFetch('/api/combined/summary')
  if (!r.ok) throw new Error(`combined summary: ${r.status}`)
  return r.json()
}
