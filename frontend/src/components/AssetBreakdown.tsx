import type { AssetPosition } from '../types'
import { formatAUD, formatPct, getPnlClass } from '../utils/pnl'

interface Props {
  positions: AssetPosition[]
}

export default function AssetBreakdown({ positions }: Props) {
  return (
    <div className="bg-gray-800 rounded-xl p-6">
      <h2 className="text-lg font-semibold text-white mb-4">Asset Breakdown</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-400 border-b border-gray-700">
            <th className="text-left pb-3">Asset</th>
            <th className="text-right pb-3">Qty</th>
            <th className="text-right pb-3">Price</th>
            <th className="text-right pb-3">Value</th>
            <th className="text-right pb-3">Allocation</th>
            <th className="text-right pb-3">Cost Basis</th>
            <th className="text-right pb-3">Unrealised P&L</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.asset} className="border-b border-gray-700 hover:bg-gray-700/50">
              <td className="py-3 font-medium text-white">{p.asset}</td>
              <td className="py-3 text-right text-gray-300">{p.quantity.toFixed(4)}</td>
              <td className="py-3 text-right text-gray-300">{formatAUD(p.price_aud)}</td>
              <td className="py-3 text-right text-white font-medium">{formatAUD(p.value_aud)}</td>
              <td className="py-3 text-right text-gray-300">{formatPct(p.allocation_pct)}</td>
              <td className="py-3 text-right text-gray-300">{formatAUD(p.cost_basis_aud)}</td>
              <td className={`py-3 text-right font-medium ${getPnlClass(p.unrealised_pnl_aud)}`}>
                {formatAUD(p.unrealised_pnl_aud)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
