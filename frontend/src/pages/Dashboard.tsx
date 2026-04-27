import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import SummaryBar from '../components/SummaryBar'
import type { Range } from '../components/SummaryBar'
import PortfolioLineChart from '../components/PortfolioLineChart'
import AssetBreakdown from '../components/AssetBreakdown'
import DCAHistoryTable from '../components/DCAHistoryTable'
import AgentInput from '../components/AgentInput'
import AgentPanel from '../components/AgentPanel'
import SignOutButton from '../components/SignOutButton'
import { useAgentChat } from '../hooks/useAgentChat'
import { SERVER_ERROR_EVENT, type ServerErrorDetail } from '../api/client'
import ErrorBanner from '../components/ErrorBanner'

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

const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '1Y': 365,
  ALL: null,
}

function filterByRange(snapshots: PortfolioSnapshot[], range: Range): PortfolioSnapshot[] {
  const days = RANGE_DAYS[range]
  if (days === null) return snapshots
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snapshots.filter((s) => new Date(s.captured_at) >= cutoff)
}

interface DashboardProps {
  onSignedOut: () => void
}

export default function Dashboard({ onSignedOut }: DashboardProps) {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    snapshots: [],
    dcaHistory: [],
    errors: {},
  })
  const [refreshing, setRefreshing] = useState(false)
  const [range, setRange] = useState<Range>('1M')
  const [panelOpen, setPanelOpen] = useState(false)
  const agent = useAgentChat()
  const [serverError, setServerError] = useState<ServerErrorDetail | null>(null)

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
    // Successful refresh clears any banner from a previous failed call.
    if (summaryResult.status === 'fulfilled') {
      setServerError(null)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Close agent panel on Escape (open is via Cmd+K from AgentInput, or input focus)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && panelOpen) {
        setPanelOpen(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [panelOpen])

  useEffect(() => {
    function handleServerError(e: Event) {
      const detail = (e as CustomEvent<ServerErrorDetail>).detail
      setServerError(detail)
    }
    window.addEventListener(SERVER_ERROR_EVENT, handleServerError)
    return () => window.removeEventListener(SERVER_ERROR_EVENT, handleServerError)
  }, [])

  function handleAgentSubmit(content: string) {
    setPanelOpen(true)
    agent.send(content)
  }

  const { summary, snapshots, dcaHistory, errors } = state
  const filteredSnapshots = useMemo(() => filterByRange(snapshots, range), [snapshots, range])
  const hasAnyError = Boolean(errors.summary || errors.snapshots || errors.dca)
  const hasAnyData = summary !== null || snapshots.length > 0 || dcaHistory.length > 0

  return (
    <div className="flex min-h-screen bg-surface text-txt-primary font-sans">
      <main className="flex-1 min-w-0">
        {/* Agent input pill — top right */}
        <div className="px-6 pt-6">
          <div className="max-w-7xl mx-auto flex items-center justify-end gap-4">
            <div className="border border-surface-border rounded-md px-3 py-1.5 hover:border-kraken/50 transition-colors">
              <AgentInput
                onSubmit={handleAgentSubmit}
                onFocus={() => setPanelOpen(true)}
                panelOpen={panelOpen}
              />
            </div>
            <SignOutButton onSignedOut={onSignedOut} />
          </div>
        </div>

      {/* Hero: portfolio value + deltas */}
      {summary ? (
        <SummaryBar
          summary={summary}
          snapshots={filteredSnapshots}
          range={range}
          onRefresh={refresh}
          refreshing={refreshing}
        />
      ) : (
        <header className="px-6 pt-10 pb-8">
          <div className="max-w-7xl mx-auto">
            <p className="text-sm font-medium text-txt-muted mb-2">Portfolio value</p>
            <p className={`text-hero font-bold font-mono text-txt-muted ${!errors.summary ? 'animate-pulse-subtle' : ''}`}>
              {errors.summary ?? '—'}
            </p>
            {errors.summary && (
              <button
                type="button"
                onClick={refresh}
                disabled={refreshing}
                className="mt-4 text-xs text-kraken hover:text-kraken-light active:scale-[0.97] font-medium disabled:opacity-50 transition-[colors,transform]"
              >
                {refreshing ? 'Loading…' : 'Retry'}
              </button>
            )}
          </div>
        </header>
      )}

      {/* Server error banner (5xx) */}
      {serverError && (
        <ErrorBanner
          detail={serverError}
          onRetry={() => {
            setServerError(null)
            refresh()
          }}
          onDismiss={() => setServerError(null)}
        />
      )}

      {/* Stale-data banner */}
      {hasAnyError && hasAnyData && (
        <div
          className="bg-loss/10 border-b border-loss/20 px-6 py-2 text-sm text-loss"
          role="alert"
          aria-live="polite"
        >
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <span>Refresh failed — showing cached data.</span>
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              className="px-3 py-1 bg-loss/20 hover:bg-loss/30 active:scale-[0.97] disabled:opacity-50 text-loss rounded text-xs font-medium transition-[colors,transform]"
            >
              {refreshing ? 'Retrying…' : 'Retry'}
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-6">

        {/* Chart */}
        <div className="pt-2 pb-12">
          {snapshots.length > 0 ? (
            <PortfolioLineChart
              snapshots={filteredSnapshots}
              range={range}
              onRangeChange={setRange}
            />
          ) : errors.snapshots ? (
            <div className="text-base text-loss" role="status" aria-live="polite">
              Chart unavailable: {errors.snapshots}
            </div>
          ) : (
            <div className="text-base text-txt-muted py-8">
              No snapshot history yet — data appears after the first hourly capture.
            </div>
          )}
        </div>

        {/* Asset breakdown */}
        <div className="pb-12">
          {summary ? (
            <AssetBreakdown positions={summary.positions} />
          ) : errors.summary ? (
            <div className="text-base text-loss" role="status" aria-live="polite">
              Assets unavailable: {errors.summary}
            </div>
          ) : (
            <div className="text-base text-txt-muted animate-pulse-subtle">Loading…</div>
          )}
        </div>

        {/* DCA history */}
        <div className="border-t border-surface-border pt-10 pb-16">
          {dcaHistory.length > 0 ? (
            <DCAHistoryTable entries={dcaHistory} />
          ) : errors.dca ? (
            <div className="text-base text-loss" role="status" aria-live="polite">
              DCA history unavailable: {errors.dca}
            </div>
          ) : (
            <div className="text-base text-txt-muted">
              No DCA history yet. Sync your Kraken trades to see purchase history.
            </div>
          )}
        </div>
      </div>
      </main>

      {panelOpen && (
        <AgentPanel
          messages={agent.messages}
          activeTools={agent.activeTools}
          hitl={agent.hitl}
          thinking={agent.thinking}
          onRespondHITL={agent.respondHITL}
          onNewConversation={agent.newConversation}
          onSubmit={handleAgentSubmit}
        />
      )}
    </div>
  )
}
