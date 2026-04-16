import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { AssetPosition } from '../types'
import { formatPct, formatAUD } from '../utils/pnl'

interface Props {
  positions: AssetPosition[]
}

const COLORS: Record<string, string> = {
  ETH: '#627EEA',
  SOL: '#9945FF',
  ADA: '#0033AD',
}
const DEFAULT_COLOR = '#6B7280'

export default function AllocationPieChart({ positions }: Props) {
  const data = positions.map((p) => ({
    name: p.asset,
    value: p.allocation_pct,
    value_aud: p.value_aud,
  }))

  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <h2 className="text-lg font-semibold text-white mb-4">Allocation</h2>
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={70}
            outerRadius={110}
            dataKey="value"
            label={(props) => `${props.name} ${formatPct(props.value)}`}
            labelLine={false}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={COLORS[entry.name] ?? DEFAULT_COLOR} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name, item) => {
              const numValue = typeof value === 'number' ? value : 0
              const aud = (item.payload as { value_aud?: number } | undefined)?.value_aud ?? 0
              return [`${formatPct(numValue)} (${formatAUD(aud)})`, String(name ?? '')]
            }}
            contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px' }}
            labelStyle={{ color: '#F9FAFB' }}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
