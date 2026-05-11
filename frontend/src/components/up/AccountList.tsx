import type { UpAccount } from '../../types/up'

interface Props {
  accounts: UpAccount[]
  /** When true, omit the per-account breakdown header (page already shows it). */
  compact?: boolean
}

export default function AccountList({ accounts }: Props) {
  if (accounts.length === 0) {
    return <div className="text-sm text-txt-muted">No accounts yet.</div>
  }
  const sorted = [...accounts].sort((a, b) => b.balance_value - a.balance_value)
  return (
    <div className="space-y-px">
      {sorted.map((a, i) => (
        <div
          key={a.id}
          className={
            'flex items-baseline justify-between py-2.5' +
            (i < sorted.length - 1 ? ' border-b border-surface-border' : '')
          }
        >
          <div className="flex items-baseline gap-3">
            <span className="text-sm text-txt-primary">{a.display_name}</span>
            <span className="text-[10px] font-medium uppercase tracking-wider text-txt-muted">
              {a.account_type === 'TRANSACTIONAL' ? 'Spending' :
               a.account_type === 'SAVER' ? 'Saver' :
               a.account_type === 'HOME_LOAN' ? 'Home loan' :
               a.account_type}
            </span>
          </div>
          <div className="font-mono text-sm text-txt-primary tabular-nums">
            ${a.balance_value.toLocaleString('en-AU', { minimumFractionDigits: 2 })}
          </div>
        </div>
      ))}
    </div>
  )
}
