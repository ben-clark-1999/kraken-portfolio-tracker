import type { UpAccount } from '../../types/up'

interface Props { accounts: UpAccount[] }

export default function AccountList({ accounts }: Props) {
  if (accounts.length === 0) {
    return <div className="text-sm text-txt-muted">No accounts yet.</div>
  }
  const total = accounts.reduce((s, a) => s + a.balance_value, 0)
  return (
    <div>
      <div className="text-sm text-txt-secondary mb-1">Total cash</div>
      <div className="text-3xl font-semibold mb-4 text-txt-primary">
        ${total.toLocaleString('en-AU', { minimumFractionDigits: 2 })}
      </div>
      <div className="space-y-1">
        {[...accounts].sort((a, b) => b.balance_value - a.balance_value).map(a => (
          <div key={a.id} className="flex justify-between py-2 border-b border-surface-border">
            <div>
              <div className="text-sm text-txt-primary">{a.display_name}</div>
              <div className="text-xs text-txt-muted">{a.account_type}</div>
            </div>
            <div className="font-mono text-sm text-txt-primary">
              ${a.balance_value.toLocaleString('en-AU', { minimumFractionDigits: 2 })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
