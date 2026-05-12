import { useMemo } from 'react'
import {
  Area, ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { PortfolioSummary, PortfolioSnapshot } from '../types'
import { formatAUD } from '../utils/pnl'
import { getAssetColor } from '../utils/assetColors'
import { unionAssetKeys, computeRangeDelta } from '../utils/portfolioRange'

export type Range = '1W' | '1M' | '3M' | '1Y' | 'ALL'
type View = 'total' | 'per-asset'

const RANGE_OPTIONS: Range[] = ['1W', '1M', '3M', '1Y', 'ALL']

interface Props {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  range: Range
  onRangeChange: (range: Range) => void
  view: View
  onViewChange: (view: View) => void
  onRefresh: () => void
  refreshing: boolean
  summaryError?: string
  snapshotsError?: string
}

function formatRelativeTime(isoString: string): string {
  const d = new Date(isoString)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const time = d.toLocaleTimeString('en-AU', {
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
  if (isToday) return time
  return `${d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })}, ${time}`
}

function formatAxisDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('en-AU', {
    day: '2-digit', month: 'short', timeZone: 'Australia/Sydney',
  })
}

interface TooltipPayloadEntry {
  value: number
  name: string
  color: string
  dataKey: string
}

function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-md border border-surface-border bg-surface-raised/95 backdrop-blur-sm px-3 py-2 shadow-lg pointer-events-none">
      <div className="flex flex-col gap-1">
        {payload
          .filter((p) => p.dataKey !== 'totalGlow')
          .map((p) => (
            <div key={p.dataKey} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: p.color }}
              />
              <span className="text-xs text-txt-muted font-medium">{p.name}</span>
              <span className="ml-auto font-mono text-sm text-txt-primary">
                {formatAUD(p.value)}
              </span>
            </div>
          ))}
      </div>
      {label && (
        <div className="mt-1 pt-1 border-t border-surface-border/50 text-[10px] text-txt-muted">
          {label}
        </div>
      )}
    </div>
  )
}

function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={spinning ? 'animate-spin' : ''}
      aria-hidden="true"
    >
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </svg>
  )
}

export default function ChartCard({
  summary, snapshots, range, onRangeChange, view, onViewChange,
  onRefresh, refreshing, summaryError, snapshotsError,
}: Props) {
  const data = useMemo(() => snapshots.map((s) => {
    const row: Record<string, number | string> = {
      date: s.captured_at,
      dateLabel: formatAxisDate(s.captured_at),
      total: s.total_value_aud,
    }
    for (const [asset, info] of Object.entries(s.assets)) {
      row[asset] = info.value_aud
    }
    return row
  }), [snapshots])

  const assets = useMemo(() => unionAssetKeys(snapshots), [snapshots])
  const rangeDelta = useMemo(() => computeRangeDelta(snapshots), [snapshots])

  const balance = summary?.total_value_aud ?? null
  const lastUpdated = summary?.captured_at

  const deltaSign = rangeDelta === null ? null : rangeDelta >= 0 ? 'pos' : 'neg'
  const deltaTone =
    deltaSign === 'pos'
      ? 'bg-profit/10 text-profit border-profit/20'
      : deltaSign === 'neg'
        ? 'bg-loss/10 text-loss border-loss/20'
        : ''

  return (
    <section
      aria-label="Portfolio value"
      className="bg-surface-raised border border-surface-border rounded-lg p-6"
    >
      {/* Zone 1 — balance hero row */}
      <div className="flex items-start justify-between gap-6 mb-5">
        <div className="flex items-start gap-3 min-w-0">
          <span
            aria-hidden="true"
            className="mt-1 inline-flex h-7 w-7 items-center justify-center rounded-md bg-kraken/15"
          >
            <span className="h-2 w-2 rounded-full bg-kraken" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-txt-muted leading-none mb-2">
              Balance
            </p>
            <div className="flex items-baseline gap-2 flex-wrap">
              {balance !== null ? (
                <span className="text-4xl sm:text-5xl font-bold font-mono text-txt-primary">
                  {formatAUD(balance)}
                </span>
              ) : (
                <span className={`text-4xl sm:text-5xl font-bold font-mono text-txt-muted ${!summaryError ? 'animate-pulse-subtle' : ''}`}>
                  {summaryError ?? '—'}
                </span>
              )}
              <span className="text-base text-txt-muted font-medium">AUD</span>
              {rangeDelta !== null && (
                <span
                  className={`ml-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-mono font-medium ${deltaTone}`}
                  aria-label={`${rangeDelta >= 0 ? 'up' : 'down'} ${Math.abs(rangeDelta).toFixed(1)} percent over ${range}`}
                >
                  {rangeDelta >= 0 ? '+' : ''}
                  {rangeDelta.toFixed(1)}% · {range}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {lastUpdated && (
            <span className="text-xs text-txt-muted whitespace-nowrap hidden sm:inline">
              Last updated {formatRelativeTime(lastUpdated)}
            </span>
          )}
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="Refresh portfolio"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-surface-border text-txt-secondary hover:text-txt-primary hover:border-kraken/40 active:scale-95 disabled:opacity-50 transition-[colors,transform]"
          >
            <RefreshIcon spinning={refreshing} />
          </button>
        </div>
      </div>

      {/* Zone 2 — controls row */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <div role="tablist" aria-label="Time range" className="flex items-center gap-1 rounded-md bg-surface/40 p-1">
          {RANGE_OPTIONS.map((r) => {
            const active = r === range
            return (
              <button
                key={r}
                role="tab"
                aria-selected={active}
                type="button"
                onClick={() => onRangeChange(r)}
                className={[
                  'rounded px-2.5 py-1 text-xs font-medium font-mono tracking-tight',
                  'transition-[background-color,color] duration-150',
                  active
                    ? 'bg-accent/15 text-accent'
                    : 'text-txt-muted hover:text-txt-primary',
                ].join(' ')}
              >
                {r}
              </button>
            )
          })}
        </div>

        <span className="h-4 w-px bg-surface-border" aria-hidden="true" />

        <div role="tablist" aria-label="View mode" className="flex items-center gap-1 rounded-md bg-surface/40 p-1">
          {(['total', 'per-asset'] as View[]).map((v) => {
            const active = v === view
            return (
              <button
                key={v}
                role="tab"
                aria-selected={active}
                type="button"
                onClick={() => onViewChange(v)}
                className={[
                  'rounded px-2.5 py-1 text-xs font-medium tracking-tight',
                  'transition-[background-color,color] duration-150',
                  active
                    ? 'bg-accent/15 text-accent'
                    : 'text-txt-muted hover:text-txt-primary',
                ].join(' ')}
              >
                {v === 'total' ? 'Total' : 'Per asset'}
              </button>
            )
          })}
        </div>

        {view === 'per-asset' && (
          <div className="flex items-center gap-3 ml-2">
            {assets.map((asset) => (
              <span key={asset} className="inline-flex items-center gap-1.5 text-xs text-txt-secondary font-mono">
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: getAssetColor(asset) }}
                />
                {asset}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Zone 3 — chart */}
      <div className="h-[320px]">
        {snapshots.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-sm text-txt-muted">
              {snapshotsError
                ? `Chart unavailable: ${snapshotsError}`
                : 'No snapshot history yet — data appears after the first hourly capture.'}
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
              <defs>
                <linearGradient id="totalFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5EEAD4" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#5EEAD4" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgb(240 238 245 / 0.06)" vertical={false} />
              <XAxis
                dataKey="dateLabel"
                stroke="#5f5a70"
                tick={{ fontSize: 11, fill: '#9691a8' }}
                tickLine={false}
                axisLine={{ stroke: 'rgb(240 238 245 / 0.06)' }}
                minTickGap={48}
              />
              <YAxis
                stroke="#5f5a70"
                tick={{ fontSize: 11, fill: '#9691a8' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(0)}k`}
                width={48}
              />
              <Tooltip
                content={<ChartTooltip />}
                cursor={{
                  stroke: 'rgb(240 238 245 / 0.18)',
                  strokeDasharray: '4 4',
                  strokeWidth: 1,
                }}
              />
              {view === 'total' ? (
                <>
                  <Line
                    type="monotone"
                    dataKey="total"
                    name="Total"
                    stroke="#5EEAD4"
                    strokeOpacity={0.35}
                    strokeWidth={6}
                    dot={false}
                    isAnimationActive={false}
                    activeDot={false}
                    legendType="none"
                  />
                  <Area
                    type="monotone"
                    dataKey="total"
                    name="Total"
                    stroke="#5EEAD4"
                    strokeWidth={1.75}
                    fill="url(#totalFill)"
                    isAnimationActive={false}
                    activeDot={{ r: 5, fill: '#5EEAD4', stroke: '#0f0e14', strokeWidth: 2 }}
                  />
                </>
              ) : (
                assets.map((asset) => (
                  <Line
                    key={asset}
                    type="monotone"
                    dataKey={asset}
                    name={asset}
                    stroke={getAssetColor(asset)}
                    strokeWidth={1.75}
                    dot={false}
                    isAnimationActive={false}
                    activeDot={{ r: 4, fill: getAssetColor(asset), stroke: '#0f0e14', strokeWidth: 2 }}
                  />
                ))
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}
