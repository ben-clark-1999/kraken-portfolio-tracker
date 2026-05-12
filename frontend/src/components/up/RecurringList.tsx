import type { RecurringCharge } from '../../types/up'

interface Props { charges: RecurringCharge[] }

const CADENCE_LABEL: Record<RecurringCharge['cadence'], string> = {
  weekly: 'Weekly',
  fortnightly: 'Fortnightly',
  monthly: 'Monthly',
  yearly: 'Yearly',
}

function fmt(n: number): string {
  return n.toLocaleString('en-AU', { minimumFractionDigits: 2 })
}

function formatNextDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })
}

export default function RecurringList({ charges }: Props) {
  if (charges.length === 0) {
    return (
      <div className="text-sm text-txt-muted">
        No recurring charges detected. A subscription needs to charge regularly
        with a stable amount before we can spot it (3 monthly charges, or 2 yearly).
      </div>
    )
  }

  const totalMonthly = charges.reduce((s, c) => s + c.monthly_equivalent, 0)

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-1">
        <span className="font-mono text-3xl text-txt-primary tabular-nums">
          ${fmt(totalMonthly)}<span className="text-base text-txt-secondary font-normal">/mo</span>
        </span>
        <span className="text-xs font-medium text-txt-muted tabular-nums">
          {charges.length} active
        </span>
      </div>
      <p className="text-xs text-txt-muted mb-4">total recurring</p>

      <ul className="divide-y divide-surface-border">
        {charges.map(c => (
          <li key={c.name + c.cadence} className="grid grid-cols-[1fr_auto] items-baseline gap-x-4 py-2.5">
            <div className="min-w-0">
              <div className="text-sm text-txt-primary truncate">{c.name}</div>
              <div className="text-xs text-txt-muted mt-0.5">
                {CADENCE_LABEL[c.cadence]}
                {c.cadence === 'yearly' && ` $${fmt(c.median_amount)}`}
                {' · next '}
                {formatNextDate(c.next_expected_at)}
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono text-sm text-txt-primary tabular-nums">
                ${fmt(c.monthly_equivalent)}
              </div>
              <div className="text-xs text-txt-muted mt-0.5">
                {c.cadence === 'yearly' ? '/mo equiv' : '/mo'}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
