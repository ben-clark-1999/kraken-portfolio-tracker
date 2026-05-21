import type { ExecutionMode, LeaderboardRow } from '../../types/strategies'

interface Props {
  rows: LeaderboardRow[]
  onRowClick: (id: string) => void
}

const AUD = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const COUNT = new Intl.NumberFormat('en-AU')

function formatAud(value: string): string {
  const n = Number(value)
  return Number.isFinite(n) ? AUD.format(n) : '—'
}

function formatPctSigned(value: string): { text: string; sign: 'pos' | 'neg' | 'zero' } {
  const n = Number(value)
  if (!Number.isFinite(n)) return { text: '—', sign: 'zero' }
  const sign = n > 0 ? 'pos' : n < 0 ? 'neg' : 'zero'
  const prefix = n > 0 ? '+' : ''
  return { text: `${prefix}${n.toFixed(2)}%`, sign }
}

function formatMaxDd(value: string): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `-${Math.abs(n).toFixed(2)}%`
}

function formatSharpe(value: string): string {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(2) : '—'
}

function formatCostInt(value: string): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `$${Math.round(n)}`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' })
}

function isWithinDays(iso: string | null, days: number): boolean {
  if (!iso) return false
  const stable = new Date(iso).getTime()
  const cutoff = Date.now() - days * 86_400_000
  return stable >= cutoff
}

function PctCell({ value, stableSince, days }: { value: string; stableSince: string | null; days: number }) {
  const { text, sign } = formatPctSigned(value)
  const tone =
    sign === 'pos' ? 'text-profit' : sign === 'neg' ? 'text-loss' : 'text-txt-secondary'
  const unstable = isWithinDays(stableSince, days)
  return (
    <td className="px-3 py-3 text-right font-mono tabular-nums">
      <span className={tone}>{text}</span>
      {unstable && stableSince && (
        <span
          aria-label={`Persona prompt changed ${formatDate(stableSince)}; comparison may not be apples-to-apples.`}
          title={`Persona prompt changed ${formatDate(stableSince)}; comparison may not be apples-to-apples.`}
          className="ml-1 text-txt-muted cursor-help select-none"
        >
          *
        </span>
      )}
    </td>
  )
}

function ModeBadge({ mode }: { mode: ExecutionMode }) {
  if (mode === 'llm_agent') {
    return (
      <span
        className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide bg-kraken/15 text-kraken-light ring-1 ring-kraken/25"
      >
        LLM
      </span>
    )
  }
  if (mode === 'manual') {
    return (
      <span
        className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide bg-surface-border/60 text-txt-secondary ring-1 ring-surface-border"
      >
        MANUAL
      </span>
    )
  }
  // deterministic
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide bg-surface-border/60 text-txt-secondary ring-1 ring-surface-border"
    >
      RULES
    </span>
  )
}

function StatusCell({ status }: { status: LeaderboardRow['status'] }) {
  const dot =
    status === 'active'
      ? 'bg-profit'
      : status === 'paused'
      ? 'bg-txt-secondary'
      : 'bg-transparent ring-1 ring-txt-muted'
  const tone =
    status === 'active'
      ? 'text-txt-primary'
      : status === 'paused'
      ? 'text-txt-secondary'
      : 'text-txt-muted'
  const label = status[0].toUpperCase() + status.slice(1)
  return (
    <td className="px-3 py-3 text-right">
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden="true" className={['h-1.5 w-1.5 rounded-full', dot].join(' ')} />
        <span className={['text-xs', tone].join(' ')}>{label}</span>
      </span>
    </td>
  )
}

export default function LeaderboardTable({ rows, onRowClick }: Props) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-surface-border/60 bg-surface-raised/40 px-8 py-10 text-center max-w-md mx-auto">
        <h3 className="text-base font-medium tracking-tight text-txt-primary">No strategies yet</h3>
        <p className="mt-2 text-sm text-txt-secondary leading-relaxed">
          Paper-trading strategies seed automatically when the sandbox boots.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs font-medium uppercase tracking-wider text-txt-muted">
            <th scope="col" className="px-3 py-2 text-right w-12">#</th>
            <th scope="col" className="px-3 py-2 text-left">Strategy</th>
            <th scope="col" className="px-3 py-2 text-right">Equity AUD</th>
            <th scope="col" className="px-3 py-2 text-right">7d</th>
            <th scope="col" className="px-3 py-2 text-right">30d</th>
            <th scope="col" className="px-3 py-2 text-right">All-time</th>
            <th scope="col" className="px-3 py-2 text-right">Sharpe</th>
            <th scope="col" className="px-3 py-2 text-right">Max DD</th>
            <th scope="col" className="px-3 py-2 text-right">Trades</th>
            <th
              scope="col"
              className="px-3 py-2 text-right"
              title="30d AUD cost — converted from USD model billing at time of each call."
            >
              Cost 30d
            </th>
            <th scope="col" className="px-3 py-2 text-right">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border/60">
          {rows.map((row, idx) => {
            // Manual is a virtual row — there's no detail drawer for it
            // (no per-strategy endpoints exist), so it's non-interactive.
            const isManual = row.id === 'manual'
            return (
            <tr
              key={row.id}
              role={isManual ? undefined : 'button'}
              tabIndex={isManual ? -1 : 0}
              aria-label={isManual ? undefined : `Open ${row.name} details`}
              onClick={isManual ? undefined : () => onRowClick(row.id)}
              onKeyDown={isManual ? undefined : e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onRowClick(row.id)
                }
              }}
              className={[
                isManual
                  ? 'bg-kraken/[0.04]'
                  : 'cursor-pointer hover:bg-surface-hover/50 focus:bg-surface-hover/60 outline-none',
              ].join(' ')}
            >
              <td className="px-3 py-3 text-right text-txt-muted font-mono tabular-nums">
                {idx + 1}
              </td>
              <td className="px-3 py-3">
                <div className="flex items-center gap-2.5">
                  <span className="font-medium text-txt-primary tracking-tight">{row.name}</span>
                  <ModeBadge mode={row.execution_mode} />
                </div>
              </td>
              <td className="px-3 py-3 text-right font-mono tabular-nums text-txt-primary">
                {formatAud(row.equity_aud)}
              </td>
              <PctCell value={row.return_7d_pct} stableSince={row.persona_prompt_stable_since} days={7} />
              <PctCell value={row.return_30d_pct} stableSince={row.persona_prompt_stable_since} days={30} />
              <PctCell value={row.return_all_time_pct} stableSince={null} days={0} />
              <td className="px-3 py-3 text-right font-mono tabular-nums text-txt-secondary">
                {formatSharpe(row.sharpe)}
              </td>
              <td className="px-3 py-3 text-right font-mono tabular-nums text-loss">
                {formatMaxDd(row.max_drawdown_pct)}
              </td>
              <td className="px-3 py-3 text-right font-mono tabular-nums text-txt-secondary">
                {COUNT.format(row.trades)}
              </td>
              <td className="px-3 py-3 text-right font-mono tabular-nums text-txt-secondary">
                {formatCostInt(row.cost_30d_aud)}
              </td>
              <StatusCell status={row.status} />
            </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
