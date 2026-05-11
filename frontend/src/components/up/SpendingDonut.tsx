import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'

interface Props {
  /** Map of category → AUD spend */
  breakdown: Record<string, number>
}

const COLORS = ['#7B61FF', '#5EEAD4', '#22D3EE', '#60A5FA', '#A78BFA', '#34D399', '#F59E0B']

function prettify(slug: string): string {
  return slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function fmt(n: number): string {
  return `$${n.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

export default function SpendingDonut({ breakdown }: Props) {
  const data = Object.entries(breakdown)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)

  if (data.length === 0) {
    return <div className="text-sm text-txt-muted">No spending in range.</div>
  }

  const total = data.reduce((s, d) => s + d.value, 0)

  return (
    <div className="grid grid-cols-1 sm:grid-cols-[10rem_1fr] items-center gap-x-8 gap-y-4">
      {/* Donut with total in the centre */}
      <div className="relative h-40 w-40">
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              innerRadius={50}
              outerRadius={75}
              stroke="none"
              isAnimationActive={false}
            >
              {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-[10px] font-medium uppercase tracking-wider text-txt-muted">Total</span>
          <span className="font-mono text-sm text-txt-primary tabular-nums mt-0.5">
            ${total.toLocaleString('en-AU', { maximumFractionDigits: 0 })}
          </span>
        </div>
      </div>

      {/* Category breakdown */}
      <ul className="text-sm space-y-px">
        {data.map((d, i) => {
          const pct = (d.value / total) * 100
          return (
            <li
              key={d.name}
              className={
                'grid grid-cols-[auto_1fr_auto_auto] items-baseline gap-x-3 py-1.5' +
                (i < data.length - 1 ? ' border-b border-surface-border' : '')
              }
            >
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm self-center"
                style={{ background: COLORS[i % COLORS.length] }}
              />
              <span className="text-txt-primary truncate">{prettify(d.name)}</span>
              <span className="text-xs text-txt-muted tabular-nums">{pct.toFixed(0)}%</span>
              <span className="font-mono text-txt-primary tabular-nums">{fmt(d.value)}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
