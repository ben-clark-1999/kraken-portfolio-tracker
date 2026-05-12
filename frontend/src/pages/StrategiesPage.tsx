import { useEffect, useState, type ReactNode } from 'react'
import { Trophy } from 'lucide-react'

import LeaderboardTable from '../components/strategies/LeaderboardTable'
import { fetchLeaderboard } from '../api/strategies'
import type { LeaderboardRow } from '../types/strategies'

export default function StrategiesPage() {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Wired into the detail drawer in Task 36; kept here so leaderboard clicks
  // already update the canonical state.
  const [, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    fetchLeaderboard()
      .then(data => { if (!cancelled) setRows(data) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true }
  }, [])

  const loading = rows === null && error === null
  const isEmpty = rows !== null && rows.length === 0
  const hasRows = rows !== null && rows.length > 0

  return (
    <main className="min-h-screen bg-surface text-txt-primary font-sans">
      <div className="max-w-7xl mx-auto px-6">

        <header className="pt-10 pb-2 flex items-start justify-between gap-6 flex-wrap">
          <div>
            <h1 className="text-2xl font-medium tracking-tight text-txt-primary">
              Strategies
            </h1>
            <p className="mt-1 text-sm text-txt-secondary">
              Multi-strategy paper-trading sandbox
            </p>
          </div>
          <div
            data-slot="system-status-banner"
            className="min-h-[28px]"
            aria-hidden="true"
          >
            {/* SystemStatusBanner mounts in Task 36 */}
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
              <LeaderboardTable rows={rows} onRowClick={setSelectedId} />
            </section>

            <section className="border-t border-surface-border pt-10 pb-16">
              <SectionHeader>Equity vs. benchmarks</SectionHeader>
              <div
                data-slot="equity-chart"
                className="h-72 rounded-lg border border-surface-border/60 bg-surface-raised/30 flex items-center justify-center text-sm text-txt-muted"
              >
                Chart renders in the next commit.
              </div>
            </section>
          </>
        )}

      </div>
    </main>
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
      <div className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-kraken/12 ring-1 ring-kraken/20 mb-4">
        <Trophy aria-hidden="true" strokeWidth={1.5} className="h-4 w-4 text-kraken-light" />
      </div>
      <h2 className="text-base font-medium tracking-tight text-txt-primary">
        No strategies yet
      </h2>
      <p className="mt-2 text-sm text-txt-secondary leading-relaxed">
        Paper-trading strategies seed automatically when the sandbox boots. Refresh in a moment, or check backend logs.
      </p>
    </div>
  )
}
