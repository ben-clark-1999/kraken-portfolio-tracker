import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { CombinedSnapshot } from '../../types/up'

interface TooltipPayloadEntry {
  dataKey: string
  value: number
}

interface ChartTooltipProps {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string | number
}

interface Props {
  snapshots: CombinedSnapshot[]
}

const SERIES = [
  { key: 'Total',  color: '#7B61FF', label: 'Total' },
  { key: 'Crypto', color: '#5EEAD4', label: 'Crypto' },
  { key: 'UP',     color: '#22C55E', label: 'UP cash' },
] as const

function formatTick(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })
}

function formatTooltipDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function formatAud(v: number): string {
  return `$${v.toLocaleString('en-AU', { maximumFractionDigits: 0 })}`
}

function ChartTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null
  const ordered = SERIES
    .map(s => payload.find(p => p.dataKey === s.key))
    .filter((p): p is TooltipPayloadEntry => Boolean(p))
  return (
    <div className="rounded border border-surface-border bg-surface-raised px-3 py-2 shadow-xl">
      <p className="text-xs font-medium text-txt-muted mb-1.5">
        {typeof label === 'string' ? formatTooltipDate(label) : ''}
      </p>
      <ul className="space-y-0.5">
        {ordered.map(p => (
          <li key={p.dataKey} className="flex items-center gap-3 text-xs">
            <span
              className="inline-block h-1.5 w-3 rounded-sm"
              style={{ background: SERIES.find(s => s.key === p.dataKey)?.color }}
            />
            <span className="text-txt-secondary w-12">
              {SERIES.find(s => s.key === p.dataKey)?.label}
            </span>
            <span className="font-mono text-txt-primary tabular-nums">
              {formatAud(Number(p.value))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function roundOrNull(v: number | null): number | null {
  return v === null ? null : Math.round(v)
}

export default function NetWorthChart({ snapshots }: Props) {
  const data = useMemo(
    () => snapshots.map(s => ({
      time: s.captured_at,
      Total: roundOrNull(s.total),
      Crypto: roundOrNull(s.crypto),
      UP: roundOrNull(s.up),
    })),
    [snapshots],
  )

  if (data.length === 0) {
    return (
      <div className="h-72 flex flex-col items-start justify-center">
        <p className="text-base text-txt-muted">
          No snapshot history yet.
        </p>
        <p className="mt-1 text-sm text-txt-muted">
          Combined net worth charts after the first hourly snapshot captures both crypto and UP.
        </p>
      </div>
    )
  }

  // Auto-stride X-axis so we never overcrowd ticks
  const tickInterval = Math.max(0, Math.floor(data.length / 6) - 1)

  return (
    <div className="h-72">
      <ResponsiveContainer>
        <ComposedChart
          data={data}
          margin={{ top: 12, right: 8, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="totalFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#7B61FF" stopOpacity={0.20} />
              <stop offset="100%" stopColor="#7B61FF" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="#2a2735" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="time"
            stroke="#5f5a70"
            tickLine={false}
            axisLine={{ stroke: '#2a2735' }}
            interval={tickInterval}
            tickFormatter={formatTick}
            tick={{ fontSize: 11, fill: '#9691a8' }}
            dy={6}
          />
          <YAxis
            stroke="#5f5a70"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: '#9691a8' }}
            tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
            width={56}
          />
          <Tooltip
            cursor={{ stroke: '#2a2735', strokeWidth: 1 }}
            content={<ChartTooltip />}
          />

          {/* Subtle area under the Total line for emphasis */}
          <Area
            type="monotone"
            dataKey="Total"
            stroke="none"
            fill="url(#totalFill)"
            isAnimationActive={false}
          />

          {SERIES.map(s => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              stroke={s.color}
              strokeWidth={s.key === 'Total' ? 2 : 1.5}
              strokeOpacity={s.key === 'Total' ? 1 : 0.85}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Custom legend — sits below chart, matches type hierarchy */}
      <div className="mt-3 flex items-center gap-5 text-xs font-medium text-txt-secondary">
        {SERIES.map(s => (
          <span key={s.key} className="flex items-center gap-2">
            <span
              className="inline-block h-0.5 w-4"
              style={{ background: s.color }}
            />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
