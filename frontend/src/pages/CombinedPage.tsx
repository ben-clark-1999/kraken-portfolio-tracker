import { useEffect, useMemo, useState } from 'react'

import KpiTiles from '../components/combined/KpiTiles'
import NetWorthChart from '../components/combined/NetWorthChart'
import RangePicker, { type Range, RANGE_DAYS } from '../components/combined/RangePicker'
import SyncStatusBanner from '../components/up/SyncStatusBanner'
import { useUpSyncStatus } from '../hooks/useUpSyncStatus'
import { fetchCombinedSummary, fetchCombinedSnapshots } from '../api/combined'
import type { CombinedSummary, CombinedSnapshot } from '../types/up'

function filterByRange(snapshots: CombinedSnapshot[], range: Range): CombinedSnapshot[] {
  const days = RANGE_DAYS[range]
  if (days === null) return snapshots
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snapshots.filter(s => new Date(s.captured_at) >= cutoff)
}

export default function CombinedPage() {
  const sync = useUpSyncStatus()
  const [summary, setSummary] = useState<CombinedSummary | null>(null)
  const [snapshots, setSnapshots] = useState<CombinedSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [range, setRange] = useState<Range>('3M')

  useEffect(() => {
    let cancelled = false
    setError(null)
    Promise.all([
      fetchCombinedSummary(),
      fetchCombinedSnapshots(),
    ]).then(([s, snaps]) => {
      if (cancelled) return
      setSummary(s); setSnapshots(snaps); setLoading(false)
    }).catch(e => {
      if (cancelled) return
      setError(e instanceof Error ? e.message : String(e))
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [sync?.state])

  const filteredSnapshots = useMemo(
    () => filterByRange(snapshots, range),
    [snapshots, range],
  )
  const lastSnapshot = snapshots.length > 0 ? snapshots[snapshots.length - 1].captured_at : null

  return (
    <main className="min-h-screen bg-surface text-txt-primary font-sans">
      <div className="max-w-7xl mx-auto px-6">

        {sync && sync.state !== 'ready' && (
          <div className="pt-6">
            <SyncStatusBanner status={sync} />
          </div>
        )}

        <section className="pt-10 pb-12">
          <KpiTiles summary={summary} asOf={lastSnapshot} />
        </section>

        <section className="border-t border-surface-border pt-10 pb-16">
          <div className="flex items-baseline justify-between mb-6 gap-4 flex-wrap">
            <div className="flex items-baseline gap-4">
              <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
                Net worth over time
              </h2>
              <p className="text-xs font-medium text-txt-muted">
                {filteredSnapshots.length > 0
                  ? `${filteredSnapshots.length} ${filteredSnapshots.length === 1 ? 'snapshot' : 'snapshots'}`
                  : ''}
              </p>
            </div>
            <RangePicker value={range} onChange={setRange} />
          </div>

          {loading ? (
            <div className="h-72 flex items-center justify-start text-sm text-txt-muted animate-pulse-subtle">
              Loading snapshots…
            </div>
          ) : error ? (
            <div className="text-base text-loss" role="status" aria-live="polite">
              Snapshots unavailable: {error}
            </div>
          ) : (
            <NetWorthChart snapshots={filteredSnapshots} />
          )}
        </section>

      </div>
    </main>
  )
}
