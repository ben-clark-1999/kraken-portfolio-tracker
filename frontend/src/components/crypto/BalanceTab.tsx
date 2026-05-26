import { useMemo, useState } from 'react'
import ChartCard, { type Range } from '../ChartCard'
import type { PortfolioSummary, PortfolioSnapshot } from '../../types'

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
  refreshing: boolean
  onRefresh: () => void
  summaryError?: string
  snapshotsError?: string
}

export default function BalanceTab(props: Props) {
  const [range, setRange] = useState<Range>('1M')
  const [view, setView] = useState<'total' | 'per-asset'>('total')
  const filtered = useMemo(() => filterByRange(props.snapshots, range), [props.snapshots, range])
  return (
    <ChartCard
      summary={props.summary}
      snapshots={filtered}
      range={range}
      onRangeChange={setRange}
      view={view}
      onViewChange={setView}
      onRefresh={props.onRefresh}
      refreshing={props.refreshing}
      summaryError={props.summaryError}
      snapshotsError={props.snapshotsError}
    />
  )
}
