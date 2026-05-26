import type { DCAEntry } from '../types'
import { formatAUD } from '../utils/pnl'

interface Props {
  entries: DCAEntry[]
}

export default function DCAHistoryTable({ entries }: Props) {
  return (
    <div className="bg-surface-raised border border-surface-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface/40">
            <tr className="text-txt-muted">
              <th className="text-left text-xs uppercase tracking-wider font-medium px-6 py-3">Date</th>
              <th className="text-left text-xs uppercase tracking-wider font-medium px-6 py-3">Asset</th>
              <th className="text-right text-xs uppercase tracking-wider font-medium px-6 py-3">Quantity</th>
              <th className="text-right text-xs uppercase tracking-wider font-medium px-6 py-3">Buy Price</th>
              <th className="text-right text-xs uppercase tracking-wider font-medium px-6 py-3">Cost Paid</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => {
              const date = new Date(e.acquired_at).toLocaleDateString('en-AU', {
                timeZone: 'Australia/Sydney',
                dateStyle: 'medium',
              })
              return (
                <tr
                  key={e.lot_id}
                  className="border-t border-surface-border/60 hover:bg-surface-hover/40 transition-colors"
                >
                  <td className="px-6 py-3 text-txt-secondary">{date}</td>
                  <td className="px-6 py-3 font-medium text-txt-primary">{e.asset}</td>
                  <td className="px-6 py-3 text-right text-txt-secondary tabular-nums">
                    {e.quantity.toFixed(4)}
                  </td>
                  <td className="px-6 py-3 text-right text-txt-secondary tabular-nums">
                    {formatAUD(e.cost_per_unit_aud)}
                  </td>
                  <td className="px-6 py-3 text-right text-txt-primary font-medium tabular-nums">
                    {formatAUD(e.cost_aud)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
