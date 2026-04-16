import { useState, useEffect, useCallback } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import SummaryBar from '../components/SummaryBar'
import AllocationPieChart from '../components/AllocationPieChart'
import PortfolioLineChart from '../components/PortfolioLineChart'
import AssetBreakdown from '../components/AssetBreakdown'
import DCAHistoryTable from '../components/DCAHistoryTable'

interface DashboardErrors {
  summary?: string
  snapshots?: string
  dca?: string
}

interface DashboardState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: DashboardErrors
}

function errMsg(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

function ErrorPanel({ message }: { message: string }) {
  return (
    <div
      className="bg-gray-800 rounded-xl p-6 text-red-400"
      role="status"
      aria-live="polite"
    >
      Failed to load: {message}
    </div>
  )
}

function EmptyPanel({ message }: { message: string }) {
  return <div className="bg-gray-800 rounded-xl p-6 text-gray-400">{message}</div>
}

export default function Dashboard() {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    snapshots: [],
    dcaHistory: [],
    errors: {},
  })
  const [refreshing, setRefreshing] = useState(false)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const errors: DashboardErrors = {}

    const [summaryResult, snapshotsResult, dcaResult] = await Promise.allSettled([
      fetchPortfolioSummary(),
      fetchSnapshots(),
      fetchDCAHistory(),
    ])

    const summary = summaryResult.status === 'fulfilled' ? summaryResult.value : null
    if (summaryResult.status === 'rejected') errors.summary = errMsg(summaryResult.reason)

    const snapshots = snapshotsResult.status === 'fulfilled' ? snapshotsResult.value : []
    if (snapshotsResult.status === 'rejected') errors.snapshots = errMsg(snapshotsResult.reason)

    const dcaHistory = dcaResult.status === 'fulfilled' ? dcaResult.value : []
    if (dcaResult.status === 'rejected') errors.dca = errMsg(dcaResult.reason)

    setState((prev) => ({
      summary: summary ?? prev.summary,
      snapshots: snapshots.length > 0 ? snapshots : prev.snapshots,
      dcaHistory: dcaHistory.length > 0 ? dcaHistory : prev.dcaHistory,
      errors,
    }))
    setRefreshing(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const { summary, snapshots, dcaHistory, errors } = state
  const hasAnyError = Boolean(errors.summary || errors.snapshots || errors.dca)
  const hasAnyData = summary !== null || snapshots.length > 0 || dcaHistory.length > 0

  return (
    <main className="min-h-screen bg-gray-900 text-gray-100">
      {summary ? (
        <SummaryBar summary={summary} onRefresh={refresh} refreshing={refreshing} />
      ) : (
        <div className="px-6 py-4 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
          <p className="text-gray-400">{errors.summary ?? 'Loading portfolio…'}</p>
          <button
            type="button"
            onClick={refresh}
            disabled={refreshing}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50"
          >
            {refreshing ? 'Loading…' : 'Retry'}
          </button>
        </div>
      )}

      {/* Stale-data banner: surfaces refresh failures even when prior data is being shown. */}
      {hasAnyError && hasAnyData && (
        <div
          className="bg-red-900/40 border-b border-red-700 px-6 py-2 text-sm text-red-200 flex items-center justify-between"
          role="alert"
          aria-live="polite"
        >
          <span>Refresh failed — showing cached data. Some sections may be out of date.</span>
          <button
            type="button"
            onClick={refresh}
            disabled={refreshing}
            className="px-3 py-1 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white rounded text-xs font-medium"
          >
            {refreshing ? 'Retrying…' : 'Retry'}
          </button>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            {summary ? (
              <AllocationPieChart positions={summary.positions} />
            ) : errors.summary ? (
              <ErrorPanel message={errors.summary} />
            ) : (
              <EmptyPanel message="Loading…" />
            )}
          </div>
          <div className="lg:col-span-2">
            {snapshots.length > 0 ? (
              <PortfolioLineChart snapshots={snapshots} />
            ) : errors.snapshots ? (
              <ErrorPanel message={errors.snapshots} />
            ) : (
              <EmptyPanel message="No snapshot history yet — check back after the first hourly snapshot." />
            )}
          </div>
        </div>

        {summary ? (
          <AssetBreakdown positions={summary.positions} />
        ) : errors.summary ? (
          <ErrorPanel message={errors.summary} />
        ) : (
          <EmptyPanel message="Loading…" />
        )}

        {dcaHistory.length > 0 ? (
          <DCAHistoryTable entries={dcaHistory} />
        ) : errors.dca ? (
          <ErrorPanel message={errors.dca} />
        ) : (
          <EmptyPanel message="No DCA history found. Run POST /api/sync to import trade history." />
        )}
      </div>
    </main>
  )
}
