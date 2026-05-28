import AccountList from './AccountList'
import RangePicker, { type Range } from '../combined/RangePicker'
import type { UpAccount, UpTransaction } from '../../types/up'

interface Props {
  accounts: UpAccount[]
  transactions: UpTransaction[]
  accountsLoading: boolean
  loading: boolean
  range: Range
  onRangeChange: (r: Range) => void
  rangeLabel: string
}

function fmt(n: number): string {
  return `$${n.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

function fmtSigned(n: number): string {
  const sign = n < 0 ? '−' : '+'
  return `${sign}$${Math.abs(n).toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

export default function BalanceTab({
  accounts, transactions, accountsLoading, loading, range, onRangeChange, rangeLabel,
}: Props) {
  const totalCash = accounts.reduce((s, a) => s + a.balance_value, 0)

  let income = 0, expense = 0
  for (const t of transactions) {
    if (t.amount_value >= 0) income += t.amount_value
    else expense += Math.abs(t.amount_value)
  }
  const net = income - expense

  return (
    <div className="max-w-3xl mx-auto">
      <header className="pb-10">
        <div className="flex items-baseline justify-between gap-4 flex-wrap mb-6">
          <p className="text-sm font-medium text-txt-muted">Total cash</p>
          <RangePicker value={range} onChange={onRangeChange} />
        </div>
        <p className={
          'text-5xl sm:text-6xl font-bold font-mono ' +
          (accountsLoading ? 'text-txt-muted animate-pulse-subtle' : 'text-txt-primary')
        }>
          {accountsLoading ? '—' : fmt(totalCash)}
        </p>
        {!loading && transactions.length > 0 && (
          <div className="mt-6 grid grid-cols-3 gap-x-12 gap-y-1 max-w-md">
            <Stat
              label="Income"
              value={`+$${income.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`}
              tone="profit"
            />
            <Stat
              label="Expense"
              value={`−$${expense.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`}
              tone="neutral"
            />
            <Stat
              label="Net"
              value={fmtSigned(net)}
              tone={net >= 0 ? 'profit' : 'loss'}
            />
          </div>
        )}
        {!loading && (
          <p className="mt-2 text-xs font-medium text-txt-muted">
            over {rangeLabel}
          </p>
        )}
      </header>

      <section className="border-t border-surface-border pt-8 pb-16">
        <div className="flex items-baseline justify-between gap-4 mb-4">
          <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
            Accounts
          </h2>
        </div>
        {accountsLoading ? <Skeleton /> : <AccountList accounts={accounts} />}
      </section>
    </div>
  )
}

function Stat({
  label, value, tone,
}: {
  label: string
  value: string
  tone: 'profit' | 'loss' | 'neutral'
}) {
  const toneClass =
    tone === 'profit' ? 'text-profit' :
    tone === 'loss' ? 'text-loss' :
    'text-txt-primary'
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wider text-txt-muted">{label}</p>
      <p className={`font-mono text-sm tabular-nums ${toneClass}`}>{value}</p>
    </div>
  )
}

function Skeleton() {
  return <div className="animate-pulse-subtle bg-surface-border/50 rounded h-12" />
}
