import { useState, useEffect, useCallback } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import SummaryBar from '../components/SummaryBar'
import AllocationPieChart from '../components/AllocationPieChart'
import PortfolioLineChart from '../components/PortfolioLineChart'
import AssetBreakdown from '../components/AssetBreakdown'
import DCAHistoryTable from '../components/DCAHistoryTable'

interface DashboardState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: { summary?: string; snapshots?: string; dca?: string }
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
    const errors: DashboardState['errors'] = {}

    const [summaryResult, snapshotsResult, dcaResult] = await Promise.allSettled([
      fetchPortfolioSummary(),
      fetchSnapshots(),
      fetchDCAHistory(),
    ])

    const summary =
      summaryResult.status === 'fulfilled' ? summaryResult.value : null
    if (summaryResult.status === 'rejected') errors.summary = (summaryResult.reason as Error).message

    const snapshots =
      snapshotsResult.status === 'fulfilled' ? snapshotsResult.value : []
    if (snapshotsResult.status === 'rejected') errors.snapshots = (snapshotsResult.reason as Error).message

    const dcaHistory =
      dcaResult.status === 'fulfilled' ? dcaResult.value : []
    if (dcaResult.status === 'rejected') errors.dca = (dcaResult.reason as Error).message

    setState((prev) => ({
      ...prev,
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

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100">
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

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            {summary ? (
              <AllocationPieChart positions={summary.positions} />
            ) : (
              <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
                {errors.summary ?? 'Loading…'}
              </div>
            )}
          </div>
          <div className="lg:col-span-2">
            {snapshots.length > 0 ? (
              <PortfolioLineChart snapshots={snapshots} />
            ) : (
              <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
                {errors.snapshots ?? 'No snapshot history yet — check back after the first hourly snapshot.'}
              </div>
            )}
          </div>
        </div>

        {summary ? (
          <AssetBreakdown positions={summary.positions} />
        ) : (
          <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
            {errors.summary ?? 'Loading…'}
          </div>
        )}

        {dcaHistory.length > 0 ? (
          <DCAHistoryTable entries={dcaHistory} />
        ) : (
          <div className="bg-gray-800 rounded-xl p-6 text-gray-400">
            {errors.dca ?? 'No DCA history found. Run POST /api/sync to import trade history.'}
          </div>
        )}
      </div>
    </div>
  )
}
