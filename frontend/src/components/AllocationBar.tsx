import type { AssetPosition } from '../types'
import { formatPct } from '../utils/pnl'
import { getAssetColor } from '../utils/assetColors'

interface Props {
  positions: AssetPosition[]
}

export default function AllocationBar({ positions }: Props) {
  return (
    <div className="flex items-center gap-4">
      {/* Stacked bar */}
      <div className="flex-1 flex h-2 rounded-full overflow-hidden bg-surface-border">
        {positions.map((p) => (
          <div
            key={p.asset}
            style={{
              width: `${p.allocation_pct}%`,
              backgroundColor: getAssetColor(p.asset),
            }}
          />
        ))}
      </div>
      {/* Legend */}
      <div className="flex items-center gap-3 text-sm shrink-0">
        {positions.map((p) => (
          <span key={p.asset} className="flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: getAssetColor(p.asset) }}
            />
            <span className="text-txt-secondary font-medium">{p.asset}</span>
            <span className="text-txt-muted font-mono">{formatPct(p.allocation_pct)}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
