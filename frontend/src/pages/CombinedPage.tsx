import { useEffect, useState } from 'react'

import KpiTiles from '../components/combined/KpiTiles'
import NetWorthChart from '../components/combined/NetWorthChart'
import SyncStatusBanner from '../components/up/SyncStatusBanner'
import { useUpSyncStatus } from '../hooks/useUpSyncStatus'
import { fetchCombinedSummary, fetchCombinedSnapshots } from '../api/combined'
import type { CombinedSummary, CombinedSnapshot } from '../types/up'

export default function CombinedPage() {
  const sync = useUpSyncStatus()
  const [summary, setSummary] = useState<CombinedSummary | null>(null)
  const [snapshots, setSnapshots] = useState<CombinedSnapshot[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchCombinedSummary(),
      fetchCombinedSnapshots(),
    ]).then(([s, snaps]) => {
      if (cancelled) return
      setSummary(s); setSnapshots(snaps); setLoading(false)
    }).catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [sync?.state])

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <h1 className="text-2xl font-semibold text-txt-primary">Combined Net Worth</h1>
      <SyncStatusBanner status={sync} />
      {loading ? (
        <div className="text-sm text-txt-muted">Loading…</div>
      ) : (
        <>
          <KpiTiles summary={summary} />
          <section>
            <h2 className="text-sm uppercase text-txt-secondary mb-3">Net worth over time</h2>
            <NetWorthChart snapshots={snapshots} />
          </section>
        </>
      )}
    </div>
  )
}
