import TransactionList from './TransactionList'
import RangePicker, { type Range } from '../combined/RangePicker'
import type { UpTransaction } from '../../types/up'

interface Props {
  transactions: UpTransaction[]
  loading: boolean
  range: Range
  onRangeChange: (r: Range) => void
  rangeLabel: string
}

export default function TransactionsTab({
  transactions, loading, range, onRangeChange, rangeLabel,
}: Props) {
  const count = transactions.length
  const aside = !loading && count > 0
    ? `${count}${count === 500 ? '+' : ''}`
    : undefined

  return (
    <div className="max-w-3xl mx-auto">
      <header className="pb-10">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <p className="text-sm font-medium text-txt-muted">Transactions</p>
            <p className="mt-1 text-xs font-medium text-txt-muted">over {rangeLabel}</p>
          </div>
          <RangePicker value={range} onChange={onRangeChange} />
        </div>
      </header>

      <section className="border-t border-surface-border pt-8 pb-16">
        <div className="flex items-baseline justify-between gap-4 mb-4">
          <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
            All transactions
          </h2>
          {aside && (
            <span className="text-xs font-medium text-txt-muted tabular-nums">{aside}</span>
          )}
        </div>
        {loading
          ? <div className="animate-pulse-subtle bg-surface-border/50 rounded h-32" />
          : <TransactionList transactions={transactions} />}
      </section>
    </div>
  )
}
