import { useMemo, useState } from 'react'
import AssetBreakdown from '../AssetBreakdown'
import type { PortfolioSummary, PortfolioSnapshot } from '../../types'
import type { Range } from '../ChartCard'

const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
  ALL: null,
}

function filterByRange(snaps: PortfolioSnapshot[], range: Range) {
  const days = RANGE_DAYS[range]
  if (days === null) return snaps
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snaps.filter((s) => new Date(s.captured_at) >= cutoff)
}

interface Props {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  summaryError?: string
}

export default function AssetsTab({ summary, snapshots, summaryError }: Props) {
  const [range] = useState<Range>('1M')
  const filtered = useMemo(() => filterByRange(snapshots, range), [snapshots, range])
  if (summary) return <AssetBreakdown positions={summary.positions} snapshots={filtered} />
  if (summaryError) {
    return (
      <div
        className="text-base text-loss bg-surface-raised border border-surface-border rounded-lg p-6"
        role="status"
        aria-live="polite"
      >
        Assets unavailable: {summaryError}
      </div>
    )
  }
  return (
    <div className="text-base text-txt-muted bg-surface-raised border border-surface-border rounded-lg p-6 animate-pulse-subtle">
      Loading…
    </div>
  )
}
