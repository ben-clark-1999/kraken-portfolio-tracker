import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import ChartCard, { type Range } from '../components/ChartCard'
import AssetBreakdown from '../components/AssetBreakdown'
import DCAHistoryTable from '../components/DCAHistoryTable'
import AgentInput from '../components/AgentInput'
import AgentPanel from '../components/AgentPanel'
import SignOutButton from '../components/SignOutButton'
import { useAgentChat } from '../hooks/useAgentChat'
import { SERVER_ERROR_EVENT, type ServerErrorDetail } from '../api/client'
import ErrorBanner from '../components/ErrorBanner'

interface CryptoPageErrors {
  summary?: string
  snapshots?: string
  dca?: string
}

interface CryptoPageState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: CryptoPageErrors
}

function errMsg(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
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

interface CryptoPageProps {
  onSignedOut: () => void
}

export default function CryptoPage({ onSignedOut }: CryptoPageProps) {
  const [state, setState] = useState<CryptoPageState>({
    summary: null,
    snapshots: [],
    dcaHistory: [],
    errors: {},
  })
  const [refreshing, setRefreshing] = useState(false)
  const [range, setRange] = useState<Range>('1M')
  const [view, setView] = useState<'total' | 'per-asset'>('total')
  const [panelOpen, setPanelOpen] = useState(false)
  const agent = useAgentChat()
  const [serverError, setServerError] = useState<ServerErrorDetail | null>(null)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const errors: CryptoPageErrors = {}

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
    if (summaryResult.status === 'fulfilled') {
      setServerError(null)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

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
  const filteredSnapshots = useMemo(
    () => filterByRange(snapshots, range),
    [snapshots, range],
  )
  const hasAnyError = Boolean(errors.summary || errors.snapshots || errors.dca)
  const hasAnyData = summary !== null || snapshots.length > 0 || dcaHistory.length > 0

  return (
    <div className="flex min-h-screen bg-surface text-txt-primary font-sans">
      <div className="flex-1 min-w-0">
        <div className="px-8 pt-6">
          <div className="w-full max-w-[1600px] mx-auto flex items-center justify-end gap-4">
            <AgentInput
              onSubmit={handleAgentSubmit}
              onFocus={() => setPanelOpen(true)}
              panelOpen={panelOpen}
            />
            <SignOutButton onSignedOut={onSignedOut} />
          </div>
        </div>

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

        {hasAnyError && hasAnyData && (
          <div
            className="bg-loss/10 border-b border-loss/20 px-8 py-2 text-sm text-loss"
            role="alert"
            aria-live="polite"
          >
            <div className="w-full max-w-[1600px] mx-auto flex items-center justify-between">
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

        <div className="w-full max-w-[1600px] mx-auto px-8 pt-6 pb-16 space-y-6">
          <ChartCard
            summary={summary}
            snapshots={filteredSnapshots}
            range={range}
            onRangeChange={setRange}
            view={view}
            onViewChange={setView}
            onRefresh={refresh}
            refreshing={refreshing}
            summaryError={errors.summary}
            snapshotsError={errors.snapshots}
          />

          {summary ? (
            <AssetBreakdown positions={summary.positions} snapshots={filteredSnapshots} />
          ) : errors.summary ? (
            <div className="text-base text-loss bg-surface-raised border border-surface-border rounded-lg p-6" role="status" aria-live="polite">
              Assets unavailable: {errors.summary}
            </div>
          ) : (
            <div className="text-base text-txt-muted bg-surface-raised border border-surface-border rounded-lg p-6 animate-pulse-subtle">
              Loading…
            </div>
          )}

          <div className="border-t border-surface-border pt-10">
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
      </div>

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
