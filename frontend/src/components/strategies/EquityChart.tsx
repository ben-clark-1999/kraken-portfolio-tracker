import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { EquityRange } from '../../types/strategies'

interface CurvePoint {
  ts: string
  equity_aud: string
}

interface StrategySeries {
  id: string
  name: string
  curve: CurvePoint[]
}

interface BenchmarkSet {
  btc_hodl: CurvePoint[]
  alt_basket_equal_weight: CurvePoint[]
}

interface Props {
  strategies: StrategySeries[]
  benchmarks: BenchmarkSet
  range: EquityRange
  onRangeChange: (r: EquityRange) => void
  showRangePicker?: boolean
  height?: string
}

const STRATEGY_PALETTE = [
  '#7B61FF', // kraken purple
  '#5EEAD4', // accent teal
  '#F472B6', // pink-400
  '#FBBF24', // amber-400
  '#A78BFA', // violet-400
] as const

const BENCH_KEYS = {
  btc: '__btc_hodl',
  alt: '__alt_basket',
} as const

const BENCH_META = {
  [BENCH_KEYS.btc]: { name: 'BTC HODL', color: '#94A3B8', dash: '6 3' },
  [BENCH_KEYS.alt]: { name: 'Alt basket', color: '#6B7280', dash: '3 3' },
} as const

const RANGE_ORDER: EquityRange[] = ['1d', '7d', '30d', '90d', 'all']
const RANGE_LABEL: Record<EquityRange, string> = {
  '1d': '1D',
  '7d': '7D',
  '30d': '30D',
  '90d': '90D',
  all: 'All',
}

type ChartRow = { time: string } & Record<string, number | string | undefined>

function toNum(s: string): number | undefined {
  const n = Number(s)
  return Number.isFinite(n) ? n : undefined
}

function mergeData(
  strategies: StrategySeries[],
  benchmarks: BenchmarkSet,
): ChartRow[] {
  const rows = new Map<string, ChartRow>()
  const upsert = (ts: string, key: string, value: number | undefined) => {
    if (value === undefined) return
    let row = rows.get(ts)
    if (!row) {
      row = { time: ts }
      rows.set(ts, row)
    }
    row[key] = value
  }
  for (const s of strategies) {
    for (const p of s.curve) upsert(p.ts, s.id, toNum(p.equity_aud))
  }
  for (const p of benchmarks.btc_hodl) upsert(p.ts, BENCH_KEYS.btc, toNum(p.equity_aud))
  for (const p of benchmarks.alt_basket_equal_weight) upsert(p.ts, BENCH_KEYS.alt, toNum(p.equity_aud))
  return [...rows.values()].sort((a, b) => a.time.localeCompare(b.time))
}

function formatXTick(range: EquityRange, iso: string): string {
  const d = new Date(iso)
  if (range === '1d' || range === '7d') {
    return d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })
  }
  return d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })
}

function formatY(v: number): string {
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(v % 1000 === 0 ? 0 : 1)}k`
  return `$${Math.round(v)}`
}

function formatAud2(v: number): string {
  return `$${v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatTooltipTime(iso: string, range: EquityRange): string {
  const d = new Date(iso)
  if (range === '1d' || range === '7d') {
    return d.toLocaleString('en-AU', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }
  return d.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}

interface SeriesMeta {
  key: string
  name: string
  color: string
  dash?: string
}

interface TooltipProps {
  active?: boolean
  payload?: Array<{ dataKey: string; value: number }>
  label?: string | number
  seriesByKey: Map<string, SeriesMeta>
  range: EquityRange
}

function ChartTooltip({ active, payload, label, seriesByKey, range }: TooltipProps) {
  if (!active || !payload?.length) return null
  const items = payload
    .map(p => ({ ...p, meta: seriesByKey.get(String(p.dataKey)) }))
    .filter((p): p is typeof p & { meta: SeriesMeta } => Boolean(p.meta))
  return (
    <div className="rounded border border-surface-border bg-surface-raised px-3 py-2 shadow-xl text-xs">
      <p className="font-medium text-txt-muted mb-1.5">
        {typeof label === 'string' ? formatTooltipTime(label, range) : ''}
      </p>
      <ul className="space-y-0.5">
        {items.map(p => (
          <li key={p.dataKey} className="flex items-center gap-3">
            <span
              className="inline-block h-0.5 w-4 rounded-sm shrink-0"
              style={{
                background:
                  p.meta.dash
                    ? `repeating-linear-gradient(to right, ${p.meta.color} 0 4px, transparent 4px 7px)`
                    : p.meta.color,
              }}
            />
            <span className="text-txt-secondary truncate max-w-[10rem]">{p.meta.name}</span>
            <span className="ml-auto font-mono text-txt-primary tabular-nums">
              {formatAud2(Number(p.value))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RangeButton({
  value, current, onChange,
}: { value: EquityRange; current: EquityRange; onChange: (r: EquityRange) => void }) {
  const active = value === current
  return (
    <button
      role="tab"
      aria-selected={active}
      type="button"
      onClick={() => onChange(value)}
      className={
        'px-2.5 py-1 rounded text-xs font-medium tracking-wide transition-colors ' +
        (active
          ? 'bg-kraken/20 text-txt-primary'
          : 'text-txt-secondary hover:text-txt-primary hover:bg-surface-hover')
      }
    >
      {RANGE_LABEL[value]}
    </button>
  )
}

export default function EquityChart({
  strategies,
  benchmarks,
  range,
  onRangeChange,
  showRangePicker = true,
  height = 'h-80',
}: Props) {
  const series: SeriesMeta[] = useMemo(() => {
    const strat: SeriesMeta[] = strategies.map((s, i) => ({
      key: s.id,
      name: s.name,
      color: STRATEGY_PALETTE[i % STRATEGY_PALETTE.length],
    }))
    return [
      ...strat,
      { key: BENCH_KEYS.btc, ...BENCH_META[BENCH_KEYS.btc] },
      { key: BENCH_KEYS.alt, ...BENCH_META[BENCH_KEYS.alt] },
    ]
  }, [strategies])

  const seriesByKey = useMemo(() => {
    const m = new Map<string, SeriesMeta>()
    for (const s of series) m.set(s.key, s)
    return m
  }, [series])

  const data = useMemo(() => mergeData(strategies, benchmarks), [strategies, benchmarks])
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const toggle = (key: string) => {
    setHidden(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const tickInterval = Math.max(0, Math.floor(data.length / 6) - 1)

  return (
    <div className="flex flex-col gap-4">
      {showRangePicker && (
        <div className="flex items-center justify-end">
          <div
            role="tablist"
            aria-label="Time range"
            className="inline-flex items-center gap-px rounded-md border border-surface-border bg-surface p-0.5"
          >
            {RANGE_ORDER.map(r => (
              <RangeButton key={r} value={r} current={range} onChange={onRangeChange} />
            ))}
          </div>
        </div>
      )}

      {data.length === 0 ? (
        <div className={`${height} rounded-lg border border-surface-border/60 bg-surface-raised/30 flex flex-col items-center justify-center text-center px-6`}>
          <p className="text-sm text-txt-secondary">No data yet</p>
          <p className="mt-1 text-xs text-txt-muted">
            The first equity snapshot lands at the top of the next hour.
          </p>
        </div>
      ) : (
        <div className={height}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#2a2735" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="time"
                stroke="#5f5a70"
                tickLine={false}
                axisLine={{ stroke: '#2a2735' }}
                interval={tickInterval}
                tickFormatter={iso => formatXTick(range, iso)}
                tick={{ fontSize: 11, fill: '#9691a8' }}
                dy={6}
              />
              <YAxis
                stroke="#5f5a70"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: '#9691a8' }}
                tickFormatter={formatY}
                domain={[0, 'auto']}
                width={56}
              />
              <Tooltip
                cursor={{ stroke: '#2a2735', strokeWidth: 1 }}
                content={
                  <ChartTooltip seriesByKey={seriesByKey} range={range} />
                }
              />
              {series.map(s => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name}
                  stroke={s.color}
                  strokeWidth={s.dash ? 1.25 : 1.75}
                  strokeDasharray={s.dash}
                  dot={false}
                  connectNulls
                  hide={hidden.has(s.key)}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
        {series.map(s => {
          const off = hidden.has(s.key)
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => toggle(s.key)}
              aria-pressed={!off}
              className={[
                'group flex items-center gap-2 transition-colors',
                off ? 'text-txt-muted' : 'text-txt-secondary hover:text-txt-primary',
              ].join(' ')}
            >
              <span
                aria-hidden="true"
                className="inline-block h-0.5 w-5 shrink-0 transition-opacity"
                style={{
                  background: s.dash
                    ? `repeating-linear-gradient(to right, ${s.color} 0 4px, transparent 4px 7px)`
                    : s.color,
                  opacity: off ? 0.4 : 1,
                }}
              />
              <span className={['font-medium tracking-tight', off ? 'line-through decoration-1' : ''].join(' ')}>
                {s.name}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
