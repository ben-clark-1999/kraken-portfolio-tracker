import type { DCAEntry } from '../types'
import { formatAUD, getPnlClass } from '../utils/pnl'

interface Props {
  entries: DCAEntry[]
}

export default function DCAHistoryTable({ entries }: Props) {
  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <h2 className="text-lg font-semibold text-white mb-4">DCA History</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-700">
              <th className="text-left pb-3">Date</th>
              <th className="text-left pb-3">Asset</th>
              <th className="text-right pb-3">Qty</th>
              <th className="text-right pb-3">Buy Price</th>
              <th className="text-right pb-3">Cost Paid</th>
              <th className="text-right pb-3">Current Value</th>
              <th className="text-right pb-3">P&L</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => {
              const date = new Date(e.acquired_at).toLocaleDateString('en-AU', {
                timeZone: 'Australia/Sydney',
                dateStyle: 'medium',
              })
              return (
                <tr key={e.lot_id} className="border-b border-gray-700 hover:bg-gray-700/50">
                  <td className="py-3 text-gray-300">{date}</td>
                  <td className="py-3 font-medium text-white">{e.asset}</td>
                  <td className="py-3 text-right text-gray-300">{e.quantity.toFixed(4)}</td>
                  <td className="py-3 text-right text-gray-300">{formatAUD(e.cost_per_unit_aud)}</td>
                  <td className="py-3 text-right text-gray-300">{formatAUD(e.cost_aud)}</td>
                  <td className="py-3 text-right text-white font-medium">{formatAUD(e.current_value_aud)}</td>
                  <td className={`py-3 text-right font-medium ${getPnlClass(e.unrealised_pnl_aud)}`}>
                    {formatAUD(e.unrealised_pnl_aud)}
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
