import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

interface Props {
  /** Map of category → AUD spend */
  breakdown: Record<string, number>
}

const COLORS = ['#7B61FF', '#5EEAD4', '#22D3EE', '#60A5FA', '#A78BFA', '#34D399', '#F59E0B']

export default function SpendingDonut({ breakdown }: Props) {
  const data = Object.entries(breakdown)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)

  if (data.length === 0) {
    return <div className="text-sm text-txt-muted">No spending in range.</div>
  }

  const total = data.reduce((s, d) => s + d.value, 0)

  return (
    <div className="flex items-center gap-6">
      <div className="w-40 h-40">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="value" innerRadius={45} outerRadius={75}>
              {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: '#1a1823', border: '1px solid #2a2735', fontSize: 12 }}
              formatter={(v: number) => `$${v.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex-1 text-sm">
        <div className="text-txt-secondary mb-2">Total: ${total.toLocaleString('en-AU', { minimumFractionDigits: 2 })}</div>
        <ul className="space-y-1">
          {data.map((d, i) => (
            <li key={d.name} className="flex justify-between">
              <span className="flex items-center gap-2 text-txt-primary">
                <span className="inline-block w-3 h-3 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
                {d.name}
              </span>
              <span className="font-mono text-txt-primary">${d.value.toLocaleString('en-AU', { minimumFractionDigits: 2 })}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
