import type { CombinedSummary } from '../../types/up'

interface Props { summary: CombinedSummary | null }

function fmt(n: number): string {
  return `$${n.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

export default function KpiTiles({ summary }: Props) {
  if (!summary) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {['Combined', 'Crypto', 'UP cash'].map(l => (
          <div key={l} className="p-4 bg-surface-raised rounded">
            <div className="text-xs uppercase text-txt-muted">{l}</div>
            <div className="text-xl font-mono text-txt-muted">—</div>
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="p-4 bg-surface-raised rounded">
        <div className="text-xs uppercase text-txt-secondary">Combined</div>
        <div className="text-2xl font-mono text-txt-primary">{fmt(summary.total)}</div>
      </div>
      <div className="p-4 bg-surface-raised rounded">
        <div className="text-xs uppercase text-txt-secondary">Crypto</div>
        <div className="text-2xl font-mono text-txt-primary">{fmt(summary.crypto)}</div>
      </div>
      <div className="p-4 bg-surface-raised rounded">
        <div className="text-xs uppercase text-txt-secondary">UP cash</div>
        <div className="text-2xl font-mono text-txt-primary">{fmt(summary.up)}</div>
      </div>
    </div>
  )
}
