import type { AssetPosition, PortfolioSnapshot } from '../types'
import { formatAUD, formatPct } from '../utils/pnl'
import { getAssetColor } from '../utils/assetColors'
import AllocationStackBar from './AllocationStackBar'
import Sparkline from './Sparkline'

interface Props {
  positions: AssetPosition[]
  snapshots: PortfolioSnapshot[]
}

function sparklineValues(snapshots: PortfolioSnapshot[], asset: string): number[] {
  return snapshots
    .map((s) => s.assets[asset]?.value_aud)
    .filter((v): v is number => typeof v === 'number')
}

function ArrowIcon({ direction }: { direction: 'up' | 'down' }) {
  const d = direction === 'up'
    ? 'M12 19V5 M5 12l7-7 7 7'
    : 'M12 5v14 M19 12l-7 7-7-7'
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  )
}

export default function AssetBreakdown({ positions, snapshots }: Props) {
  const sorted = [...positions]
    .filter((p) => p.value_aud > 0)
    .sort((a, b) => b.allocation_pct - a.allocation_pct)

  return (
    <section
      aria-label="Asset breakdown"
      className="bg-surface-raised border border-surface-border rounded-lg p-6"
    >
      <h2 className="text-lg font-semibold text-txt-primary mb-4">
        Asset Breakdown
      </h2>

      <div className="mb-6">
        <AllocationStackBar positions={sorted} />
      </div>

      <ul role="list" className="flex flex-col">
        {sorted.map((p, idx) => {
          const isUp = p.unrealised_pnl_aud >= 0
          const tone = isUp
            ? 'bg-profit/10 text-profit'
            : 'bg-loss/10 text-loss'
          return (
            <li
              key={p.asset}
              className={[
                'flex items-center gap-6 py-4 px-2 -mx-2 rounded-md',
                'hover:bg-surface-hover/50 transition-colors',
                idx < sorted.length - 1 ? 'border-b border-surface-border/50' : '',
              ].join(' ')}
            >
              <div className="w-20 flex items-center gap-2 shrink-0">
                <span
                  aria-hidden="true"
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: getAssetColor(p.asset) }}
                />
                <span className="text-sm font-mono font-medium text-txt-primary">
                  {p.asset}
                </span>
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-txt-primary leading-tight">
                  {p.quantity.toFixed(4)} {p.asset}
                </p>
                <p className="text-xs font-mono text-txt-muted leading-tight mt-0.5">
                  @ {formatAUD(p.price_aud)}
                </p>
              </div>

              <div className="w-32 shrink-0">
                <Sparkline
                  values={sparklineValues(snapshots, p.asset)}
                  color={getAssetColor(p.asset)}
                />
              </div>

              <div className="w-28 text-right shrink-0">
                <span className="text-base font-mono font-semibold text-txt-primary">
                  {formatAUD(p.value_aud)}
                </span>
              </div>

              <div className="w-16 text-right shrink-0">
                <span className="text-sm font-mono text-txt-muted">
                  {formatPct(p.allocation_pct)}
                </span>
              </div>

              <div className="w-32 text-right shrink-0">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-mono font-medium ${tone}`}>
                  <ArrowIcon direction={isUp ? 'up' : 'down'} />
                  {formatAUD(Math.abs(p.unrealised_pnl_aud))}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
