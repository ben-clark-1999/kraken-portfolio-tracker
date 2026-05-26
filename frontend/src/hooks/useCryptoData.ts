import { useCallback, useEffect, useState } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'

export interface CryptoDataErrors {
  summary?: string
  snapshots?: string
  dca?: string
}

export interface CryptoDataState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: CryptoDataErrors
  refreshing: boolean
  refresh: () => Promise<void>
}

function errMsg(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

export function useCryptoData(): CryptoDataState {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([])
  const [dcaHistory, setDcaHistory] = useState<DCAEntry[]>([])
  const [errors, setErrors] = useState<CryptoDataErrors>({})
  const [refreshing, setRefreshing] = useState(false)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const next: CryptoDataErrors = {}
    const [s, sn, d] = await Promise.allSettled([
      fetchPortfolioSummary(),
      fetchSnapshots(),
      fetchDCAHistory(),
    ])
    if (s.status === 'fulfilled') setSummary(s.value)
    else next.summary = errMsg(s.reason)
    if (sn.status === 'fulfilled') setSnapshots(sn.value)
    else next.snapshots = errMsg(sn.reason)
    if (d.status === 'fulfilled') setDcaHistory(d.value)
    else next.dca = errMsg(d.reason)
    setErrors(next)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { summary, snapshots, dcaHistory, errors, refreshing, refresh }
}
