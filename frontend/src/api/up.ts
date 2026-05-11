import { apiFetch } from './client'
import type {
  UpAccount, UpTransaction, CashflowRow, SyncStatus,
} from '../types/up'

export async function fetchAccounts(): Promise<UpAccount[]> {
  const r = await apiFetch('/api/up/accounts')
  if (!r.ok) throw new Error(`accounts: ${r.status}`)
  return r.json()
}

export async function fetchTransactions(opts?: {
  limit?: number; since?: string; until?: string;
}): Promise<UpTransaction[]> {
  const params = new URLSearchParams()
  if (opts?.limit) params.set('limit', String(opts.limit))
  if (opts?.since) params.set('since', opts.since)
  if (opts?.until) params.set('until', opts.until)
  const url = `/api/up/transactions${params.size ? `?${params}` : ''}`
  const r = await apiFetch(url)
  if (!r.ok) throw new Error(`transactions: ${r.status}`)
  return r.json()
}

export async function fetchSpendingSummary(
  since: string, until: string,
): Promise<Record<string, number>> {
  const r = await apiFetch(`/api/up/spending/summary?since=${encodeURIComponent(since)}&until=${encodeURIComponent(until)}`)
  if (!r.ok) throw new Error(`spending: ${r.status}`)
  return r.json()
}

export async function fetchCashflow(
  since: string, until: string, granularity: 'day' | 'week' | 'month' = 'month',
): Promise<CashflowRow[]> {
  const r = await apiFetch(`/api/up/cashflow?since=${encodeURIComponent(since)}&until=${encodeURIComponent(until)}&granularity=${granularity}`)
  if (!r.ok) throw new Error(`cashflow: ${r.status}`)
  return r.json()
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const r = await apiFetch('/api/up/sync/status')
  if (!r.ok) throw new Error(`sync status: ${r.status}`)
  return r.json()
}

export async function triggerSyncRetry(): Promise<void> {
  const r = await apiFetch('/api/up/sync/retry', { method: 'POST' })
  if (!r.ok) throw new Error(`retry: ${r.status}`)
}
