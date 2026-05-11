import type { UpTransaction } from '../../types/up'

interface Props { transactions: UpTransaction[] }

export default function TransactionList({ transactions }: Props) {
  if (transactions.length === 0) {
    return <div className="text-sm text-txt-muted">No transactions in range.</div>
  }
  return (
    <ul className="divide-y divide-surface-border">
      {transactions.map(t => (
        <li key={t.id} className="flex justify-between py-2">
          <div>
            <div className="text-sm text-txt-primary">{t.description}</div>
            <div className="text-xs text-txt-muted">{t.created_at.slice(0, 10)} · {t.status}</div>
          </div>
          <div className={`font-mono text-sm ${t.amount_value < 0 ? 'text-loss' : 'text-profit'}`}>
            {t.amount_value < 0 ? '-' : '+'}${Math.abs(t.amount_value).toLocaleString('en-AU', { minimumFractionDigits: 2 })}
          </div>
        </li>
      ))}
    </ul>
  )
}
