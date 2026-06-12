import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import LeaderboardTable from '../components/strategies/LeaderboardTable'
import EquityChart from '../components/strategies/EquityChart'
import StrategyDetailDrawer from '../components/strategies/StrategyDetailDrawer'
import SystemStatusBanner from '../components/strategies/SystemStatusBanner'
import { fetchEquityCurve, fetchLeaderboard } from '../api/strategies'
import type {
  EquityCurveResponse,
  EquityRange,
  LeaderboardRow,
} from '../types/strategies'

const EMPTY_BENCHMARKS: EquityCurveResponse['benchmarks'] = {
  btc_hodl: [],
  alt_basket_equal_weight: [],
}

// Comparison window opens 2026-05-12; banner stays visible for four weeks
// (until 2026-06-12) while the rolling window is too short to be meaningful.
const SHORT_WINDOW_CUTOFF = new Date('2026-06-12T00:00:00')

export default function StrategiesPage() {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const [range, setRange] = useState<EquityRange>('30d')
  const [curves, setCurves] = useState<EquityCurveResponse[] | null>(null)

  const loadLeaderboard = useCallback(() => {
    let cancelled = false
    setError(null)
    fetchLeaderboard()
      .then(data => { if (!cancelled) setRows(data) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => loadLeaderboard(), [loadLeaderboard])

  useEffect(() => {
    if (!rows || rows.length === 0) {
      setCurves(null)
      return
    }
    let cancelled = false
    // The 'Manual' since-launch row (id='manual') has no equity endpoint —
    // it'd just collapse to a single point at the window edge anyway, so
    // skip it on the chart. The 'Manual (all time)' row DOES have an
    // endpoint (/manual-lifetime/equity) that returns a TWR-adjusted
    // curve, so include it like a regular strategy.
    const fetchable = rows.filter(r => r.id !== 'manual')
    Promise.all(fetchable.map(r => fetchEquityCurve(r.id, range)))
      .then(responses => { if (!cancelled) setCurves(responses) })
      .catch(() => {
        if (!cancelled) setCurves([])
      })
    return () => { cancelled = true }
  }, [rows, range])

  const equitySeries = useMemo(() => {
    if (!rows || !curves) return null
    // curves[] is indexed against the Manual-filtered list above, so we
    // build the series from the same filtered view to keep indices aligned.
    const fetchable = rows.filter(r => r.id !== 'manual')
    return fetchable.map((r, i) => ({
      id: r.id,
      name: r.name,
      curve: curves[i]?.strategy ?? [],
    }))
  }, [rows, curves])

  const benchmarks = curves?.[0]?.benchmarks ?? EMPTY_BENCHMARKS

  const loading = rows === null && error === null
  const isEmpty = rows !== null && rows.length === 0
  const hasRows = rows !== null && rows.length > 0

  return (
    <main className="min-h-screen bg-surface text-txt-primary font-sans">
      <div className="max-w-[1440px] mx-auto px-8 animate-rise">

        <header className="pt-10 pb-2 flex items-start justify-between gap-6 flex-wrap">
          <div>
            <h1 className="text-2xl font-medium tracking-tight text-txt-primary">
              Strategies
            </h1>
            <p className="mt-1 text-sm text-txt-secondary">
              Multi-strategy paper-trading sandbox
            </p>
          </div>
          <div className="pt-1">
            <SystemStatusBanner />
          </div>
        </header>

        {error && (
          <section className="pt-8 pb-4">
            <div className="text-base text-loss" role="status" aria-live="polite">
              Leaderboard unavailable: {error}
            </div>
          </section>
        )}

        {loading && (
          <section className="pt-8 pb-8" aria-busy="true">
            <div className="h-4 w-32 rounded bg-surface-border/40 animate-pulse-subtle mb-6" />
            <div className="space-y-1.5">
              <div className="h-12 rounded bg-surface-border/40 animate-pulse-subtle" />
              <div className="h-12 rounded bg-surface-border/30 animate-pulse-subtle" />
              <div className="h-12 rounded bg-surface-border/20 animate-pulse-subtle" />
            </div>
          </section>
        )}

        {isEmpty && (
          <section className="pt-10 pb-20">
            <EmptyState />
          </section>
        )}

        {hasRows && rows && (
          <>
            <section className="pt-8 pb-12">
              <SectionHeader
                count={`${rows.length} ${rows.length === 1 ? 'strategy' : 'strategies'}`}
              >
                Leaderboard
              </SectionHeader>
              <ShortWindowCaveat />
              <LeaderboardTable rows={rows} onRowClick={setSelectedId} />
            </section>

            <section className="border-t border-surface-border pt-10 pb-16">
              <SectionHeader>% change vs. benchmarks</SectionHeader>
              {equitySeries ? (
                <EquityChart
                  strategies={equitySeries}
                  benchmarks={benchmarks}
                  range={range}
                  onRangeChange={setRange}
                />
              ) : (
                <div
                  className="h-80 rounded-lg bg-surface-border/30 animate-pulse-subtle"
                  aria-busy="true"
                />
              )}
            </section>
          </>
        )}

      </div>

      <StrategyDetailDrawer
        strategyId={selectedId}
        onClose={() => setSelectedId(null)}
        onStateChanged={loadLeaderboard}
      />
    </main>
  )
}

function ShortWindowCaveat() {
  if (new Date() >= SHORT_WINDOW_CUTOFF) return null
  return (
    <p role="note" className="mb-4 max-w-[65ch] text-sm leading-relaxed text-txt-muted">
      Comparisons are noisy until the window includes several weeks of varied
      market conditions. Treat numbers cautiously through mid-June 2026.
    </p>
  )
}

function SectionHeader({ children, count }: { children: ReactNode; count?: string }) {
  return (
    <div className="flex items-baseline gap-4 mb-4">
      <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
        {children}
      </h2>
      {count && (
        <p className="text-xs font-medium text-txt-muted tabular-nums">{count}</p>
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-surface-border/60 bg-surface-raised/40 px-8 py-10 text-center max-w-md mx-auto">
      <h2 className="text-base font-medium tracking-tight text-txt-primary">
        No strategies yet
      </h2>
      <p className="mt-2 text-sm text-txt-secondary leading-relaxed">
        Paper-trading strategies seed automatically when the sandbox boots. Refresh in a moment, or check backend logs.
      </p>
    </div>
  )
}
