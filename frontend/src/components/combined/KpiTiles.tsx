import type { CombinedSummary } from '../../types/up'

interface Props {
  summary: CombinedSummary | null
  /** Most recent snapshot timestamp — shown as a quiet caption under the
   *  hero, mirroring the "as of" treatment in the Crypto page. */
  asOf?: string | null
}

function fmt(n: number): string {
  return `$${n.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

function pct(part: number, total: number): string {
  if (!total) return '—'
  return `${((part / total) * 100).toFixed(1)}%`
}

function formatAsOf(iso: string): string {
  return new Date(iso).toLocaleString('en-AU', {
    timeZone: 'Australia/Sydney',
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export default function KpiTiles({ summary, asOf }: Props) {
  if (!summary) {
    return (
      <header>
        <p className="text-sm font-medium text-txt-muted mb-2">Net worth</p>
        <p className="text-5xl sm:text-6xl font-bold font-mono text-txt-muted animate-pulse-subtle">
          —
        </p>
        <div className="mt-8 grid grid-cols-2 gap-x-12 max-w-md">
          {['Crypto', 'UP cash'].map(l => (
            <div key={l}>
              <p className="text-xs font-medium uppercase tracking-wider text-txt-muted mb-1">
                {l}
              </p>
              <p className="text-xl font-mono text-txt-muted">—</p>
            </div>
          ))}
        </div>
      </header>
    )
  }

  return (
    <header>
      <p className="text-sm font-medium text-txt-muted mb-2">Net worth</p>
      <p className="text-5xl sm:text-6xl font-bold font-mono text-txt-primary">
        {fmt(summary.total)}
      </p>
      {asOf && (
        <p className="mt-2 text-xs font-medium text-txt-muted">
          as of {formatAsOf(asOf)}
        </p>
      )}

      <div className="mt-8 grid grid-cols-2 gap-x-12 max-w-md">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-txt-muted mb-1">
            Crypto
          </p>
          <p className="text-xl font-mono text-txt-primary">{fmt(summary.crypto)}</p>
          <p className="mt-1 text-xs font-medium text-txt-secondary">
            {pct(summary.crypto, summary.total)} of total
          </p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-txt-muted mb-1">
            UP cash
          </p>
          <p className="text-xl font-mono text-txt-primary">{fmt(summary.up)}</p>
          <p className="mt-1 text-xs font-medium text-txt-secondary">
            {pct(summary.up, summary.total)} of total
          </p>
        </div>
      </div>
    </header>
  )
}
