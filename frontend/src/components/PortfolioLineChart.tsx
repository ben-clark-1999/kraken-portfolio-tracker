import { useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { PortfolioSnapshot } from '../types'
import { formatAUD } from '../utils/pnl'

interface Props {
  snapshots: PortfolioSnapshot[]
}

type View = 'total' | 'per-asset'
type Range = '7d' | '30d' | 'all'

const ASSET_COLORS: Record<string, string> = {
  ETH: '#627EEA',
  SOL: '#9945FF',
  ADA: '#0033AD',
}

function filterByRange(snapshots: PortfolioSnapshot[], range: Range): PortfolioSnapshot[] {
  if (range === 'all') return snapshots
  const days = range === '7d' ? 7 : 30
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snapshots.filter((s) => new Date(s.captured_at) >= cutoff)
}

export default function PortfolioLineChart({ snapshots }: Props) {
  const [view, setView] = useState<View>('total')
  const [range, setRange] = useState<Range>('30d')

  const filtered = filterByRange(snapshots, range)
  const data = filtered.map((s) => {
    const row: Record<string, number | string> = {
      date: new Date(s.captured_at).toLocaleDateString('en-AU', { timeZone: 'Australia/Sydney' }),
      total: s.total_value_aud,
    }
    for (const [asset, info] of Object.entries(s.assets)) {
      row[asset] = info.value_aud
    }
    return row
  })

  const assets = snapshots.length > 0 ? Object.keys(snapshots[0].assets) : []

  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Portfolio Value</h2>
        <div className="flex gap-2">
          {(['7d', '30d', 'all'] as Range[]).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                range === r ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {r}
            </button>
          ))}
          <div className="w-px bg-gray-600 mx-1" />
          {(['total', 'per-asset'] as View[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                view === v ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {v === 'total' ? 'Total' : 'Per Asset'}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="date" stroke="#9CA3AF" tick={{ fontSize: 12 }} />
          <YAxis
            stroke="#9CA3AF"
            tick={{ fontSize: 12 }}
            tickFormatter={(v) => {
              const numValue = typeof v === 'number' ? v : 0
              return `$${(numValue / 1000).toFixed(0)}k`
            }}
          />
          <Tooltip
            formatter={(value) => {
              const numValue = typeof value === 'number' ? value : 0
              return [formatAUD(numValue)]
            }}
            contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
            labelStyle={{ color: '#F9FAFB' }}
          />
          <Legend />
          {view === 'total' ? (
            <Line type="monotone" dataKey="total" name="Total" stroke="#60A5FA" dot={false} strokeWidth={2} />
          ) : (
            assets.map((asset) => (
              <Line
                key={asset}
                type="monotone"
                dataKey={asset}
                name={asset}
                stroke={ASSET_COLORS[asset] ?? '#6B7280'}
                dot={false}
                strokeWidth={2}
              />
            ))
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
