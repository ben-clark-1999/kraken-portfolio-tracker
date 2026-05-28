import SpendingDonut from './SpendingDonut'
import RecurringList from './RecurringList'
import RangePicker, { type Range } from '../combined/RangePicker'
import type { RecurringCharge } from '../../types/up'

interface Props {
  spending: Record<string, number>
  recurring: RecurringCharge[]
  loading: boolean
  recurringLoading: boolean
  range: Range
  onRangeChange: (r: Range) => void
  rangeLabel: string
}

export default function SpendingTab({
  spending, recurring, loading, recurringLoading, range, onRangeChange, rangeLabel,
}: Props) {
  return (
    <div className="max-w-3xl mx-auto">
      <header className="pb-10">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <p className="text-sm font-medium text-txt-muted">Spending breakdown</p>
            <p className="mt-1 text-xs font-medium text-txt-muted">over {rangeLabel}</p>
          </div>
          <RangePicker value={range} onChange={onRangeChange} />
        </div>
      </header>

      <section className="border-t border-surface-border pt-8 pb-10">
        <div className="flex items-baseline justify-between gap-4 mb-4">
          <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
            By category
          </h2>
        </div>
        {loading ? <Skeleton /> : <SpendingDonut breakdown={spending} />}
      </section>

      <section className="border-t border-surface-border pt-8 pb-16">
        <div className="flex items-baseline justify-between gap-4 mb-4">
          <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
            Subscriptions
          </h2>
        </div>
        {recurringLoading ? <Skeleton /> : <RecurringList charges={recurring} />}
      </section>
    </div>
  )
}

function Skeleton() {
  return <div className="animate-pulse-subtle bg-surface-border/50 rounded h-32" />
}
