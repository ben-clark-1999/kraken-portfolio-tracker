import type { UpTransaction } from '../../types/up'

interface Props { transactions: UpTransaction[] }

function formatDay(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })
}

function isToday(iso: string): boolean {
  const d = new Date(iso)
  const now = new Date()
  return d.getFullYear() === now.getFullYear() &&
         d.getMonth() === now.getMonth() &&
         d.getDate() === now.getDate()
}

function isYesterday(iso: string): boolean {
  const d = new Date(iso)
  const now = new Date()
  now.setDate(now.getDate() - 1)
  return d.getFullYear() === now.getFullYear() &&
         d.getMonth() === now.getMonth() &&
         d.getDate() === now.getDate()
}

function relativeDay(iso: string): string {
  if (isToday(iso)) return 'Today'
  if (isYesterday(iso)) return 'Yesterday'
  return formatDay(iso)
}

export default function TransactionList({ transactions }: Props) {
  if (transactions.length === 0) {
    return <div className="text-sm text-txt-muted">No transactions in range.</div>
  }
  return (
    <ul className="divide-y divide-surface-border">
      {transactions.map(t => {
        const held = t.status === 'HELD'
        const outflow = t.amount_value < 0
        return (
          <li key={t.id} className="flex items-baseline justify-between py-2.5 gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 min-w-0">
                <span className={
                  'text-sm truncate ' + (held ? 'text-txt-secondary' : 'text-txt-primary')
                }>
                  {t.description}
                </span>
                {held && (
                  <span className="shrink-0 inline-block text-[10px] font-medium uppercase tracking-wider text-txt-muted border border-surface-border rounded px-1.5 py-px">
                    Held
                  </span>
                )}
              </div>
              <div className="text-xs text-txt-muted mt-0.5">{relativeDay(t.created_at)}</div>
            </div>
            <div className={
              'font-mono text-sm tabular-nums shrink-0 ' +
              (held ? 'text-txt-secondary' :
                outflow ? 'text-txt-primary' : 'text-profit')
            }>
              {outflow ? '−' : '+'}${Math.abs(t.amount_value).toLocaleString('en-AU', { minimumFractionDigits: 2 })}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
