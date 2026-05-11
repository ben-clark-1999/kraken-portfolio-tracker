import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts'
import type { CombinedSnapshot } from '../../types/up'

interface Props { snapshots: CombinedSnapshot[] }

export default function NetWorthChart({ snapshots }: Props) {
  if (snapshots.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center text-sm text-txt-muted">
        No snapshot history yet.
      </div>
    )
  }

  const data = snapshots.map(s => ({
    time: s.captured_at.slice(0, 10),
    Total: Math.round(s.total),
    Crypto: Math.round(s.crypto),
    UP: Math.round(s.up),
  }))

  return (
    <div className="h-72">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2735" />
          <XAxis dataKey="time" stroke="#9691a8" fontSize={11} />
          <YAxis stroke="#9691a8" fontSize={11} tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
          <Tooltip
            contentStyle={{ background: '#1a1823', border: '1px solid #2a2735', fontSize: 12 }}
            formatter={(v: number) => `$${v.toLocaleString('en-AU')}`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="Total" stroke="#7B61FF" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="Crypto" stroke="#5EEAD4" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="UP" stroke="#22C55E" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
