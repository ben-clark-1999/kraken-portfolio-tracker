import { formatAUD } from '../utils/pnl'
import type { PortfolioSummary } from '../types'

interface Props {
  summary: PortfolioSummary
  onRefresh: () => void
  refreshing: boolean
}

export default function SummaryBar({ summary, onRefresh, refreshing }: Props) {
  const lastUpdated = new Date(summary.captured_at).toLocaleString('en-AU', {
    timeZone: 'Australia/Sydney',
    dateStyle: 'short',
    timeStyle: 'short',
  })

  // Parse YYYY-MM-DD as a local calendar date, not UTC midnight, to avoid
  // an off-by-one shift when rendering through Intl in another timezone.
  let nextDCA = '—'
  if (summary.next_dca_date) {
    const [y, m, d] = summary.next_dca_date.split('-').map(Number)
    nextDCA = new Date(y, m - 1, d).toLocaleDateString('en-AU', {
      dateStyle: 'medium',
    })
  }

  return (
    <div className="flex items-center justify-between px-6 py-4 bg-gray-800 border-b border-gray-700">
      <div>
        <p className="text-sm text-gray-400">Portfolio Value</p>
        <p className="text-3xl font-bold text-white">{formatAUD(summary.total_value_aud)}</p>
      </div>
      <div className="flex items-center gap-8">
        <div className="text-right">
          <p className="text-sm text-gray-400">Next DCA</p>
          <p className="text-white font-medium">{nextDCA}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-400">Last updated</p>
          <p className="text-white font-medium">{lastUpdated}</p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}
