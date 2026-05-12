import { useState } from 'react'
import type { AssetPosition } from '../types'
import { getAssetColor } from '../utils/assetColors'
import { formatAUD, formatPct } from '../utils/pnl'

interface Props {
  positions: AssetPosition[]
}

export default function AllocationStackBar({ positions }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)

  const sorted = [...positions]
    .filter((p) => p.allocation_pct > 0)
    .sort((a, b) => b.allocation_pct - a.allocation_pct)

  if (sorted.length === 0) {
    return <div className="h-2.5 w-full rounded-full bg-surface-border/40" />
  }

  const tooltipFor = sorted.find((p) => p.asset === hovered)

  return (
    <div className="relative">
      <div className="h-2.5 w-full rounded-full overflow-hidden flex gap-px bg-surface-border/40">
        {sorted.map((p) => (
          <button
            key={p.asset}
            type="button"
            onMouseEnter={() => setHovered(p.asset)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(p.asset)}
            onBlur={() => setHovered(null)}
            aria-label={`${p.asset} ${formatPct(p.allocation_pct)} ${formatAUD(p.value_aud)}`}
            className="h-full transition-[filter,transform] duration-150 ease-out hover:brightness-125 focus:brightness-125 focus:outline-none"
            style={{
              flexGrow: p.allocation_pct,
              flexBasis: 0,
              backgroundColor: getAssetColor(p.asset),
            }}
          />
        ))}
      </div>

      {tooltipFor && (
        <div
          role="tooltip"
          className="absolute left-1/2 -translate-x-1/2 -top-12 z-10 pointer-events-none whitespace-nowrap rounded-md border border-surface-border bg-surface-raised/95 backdrop-blur-sm px-3 py-1.5 text-xs text-txt-primary shadow-lg"
        >
          <span className="font-mono font-medium" style={{ color: getAssetColor(tooltipFor.asset) }}>
            {tooltipFor.asset}
          </span>
          <span className="text-txt-muted"> · </span>
          <span className="font-mono">{formatPct(tooltipFor.allocation_pct)}</span>
          <span className="text-txt-muted"> · </span>
          <span className="font-mono">{formatAUD(tooltipFor.value_aud)}</span>
        </div>
      )}
    </div>
  )
}
