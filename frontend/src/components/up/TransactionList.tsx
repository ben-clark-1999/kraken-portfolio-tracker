import {
  Home, Car, User, UtensilsCrossed, ArrowDownLeft, Receipt,
  type LucideIcon,
} from 'lucide-react'
import type { UpTransaction } from '../../types/up'

interface Props { transactions: UpTransaction[] }

const PARENT_CATEGORY_ICONS: Record<string, LucideIcon> = {
  'home':       Home,
  'transport':  Car,
  'personal':   User,
  'good-life':  UtensilsCrossed,
}

function iconForTransaction(t: UpTransaction): LucideIcon {
  if (t.amount_value > 0) return ArrowDownLeft
  if (t.parent_category_id && PARENT_CATEGORY_ICONS[t.parent_category_id]) {
    return PARENT_CATEGORY_ICONS[t.parent_category_id]
  }
  return Receipt
}

function categoryLabel(parentId: string | null): string | null {
  if (!parentId) return null
  return parentId
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function formatDay(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })
}

function isToday(iso: string): boolean {
  const d = new Date(iso)
  const now = new Date()
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate()
}

function isYesterday(iso: string): boolean {
  const d = new Date(iso)
  const now = new Date()
  now.setDate(now.getDate() - 1)
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate()
}

function relativeDay(iso: string): string {
  if (isToday(iso)) return 'Today'
  if (isYesterday(iso)) return 'Yesterday'
  return formatDay(iso)
}

function formatAmount(value: number): string {
  return Math.abs(value).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export default function TransactionList({ transactions }: Props) {
  if (transactions.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-surface-border/60 px-4 py-8 text-center">
        <p className="text-sm text-txt-muted">No transactions in range.</p>
      </div>
    )
  }

  return (
    <ul role="list" className="flex flex-col gap-0.5">
      {transactions.map((t) => {
        const Icon = iconForTransaction(t)
        const held = t.status === 'HELD'
        const inflow = t.amount_value > 0
        const category = categoryLabel(t.parent_category_id)

        const amountTone = held
          ? 'text-txt-secondary'
          : inflow
            ? 'text-profit'
            : 'text-txt-primary'

        return (
          <li
            key={t.id}
            className="group flex items-center gap-3 rounded-md px-2 py-2 -mx-2 hover:bg-surface-hover/40 transition-colors"
          >
            <span
              aria-hidden="true"
              className={[
                'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border',
                held
                  ? 'border-surface-border/60 bg-surface/40'
                  : 'border-surface-border bg-surface-raised',
              ].join(' ')}
            >
              <Icon
                strokeWidth={1.5}
                className={[
                  'h-4 w-4 transition-colors',
                  held
                    ? 'text-txt-muted'
                    : inflow
                      ? 'text-profit/80'
                      : 'text-txt-secondary group-hover:text-txt-primary',
                ].join(' ')}
              />
            </span>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={[
                    'truncate text-sm font-medium tracking-tight',
                    held ? 'text-txt-secondary' : 'text-txt-primary',
                  ].join(' ')}
                >
                  {t.description}
                </span>
                {held && (
                  <span
                    className="shrink-0 inline-flex items-center gap-1 rounded px-1.5 py-px text-[10px] font-mono uppercase tracking-wider text-txt-muted border border-surface-border"
                  >
                    <span aria-hidden="true" className="h-1 w-1 rounded-full bg-txt-muted animate-pulse" />
                    Held
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 text-xs text-txt-muted">
                <span className="font-mono tracking-tight">{relativeDay(t.created_at)}</span>
                {category && (
                  <>
                    <span aria-hidden="true" className="h-0.5 w-0.5 rounded-full bg-txt-muted/60" />
                    <span className="truncate">{category}</span>
                  </>
                )}
              </div>
            </div>

            <div className="text-right shrink-0">
              <span className={`font-mono text-sm tabular-nums ${amountTone}`}>
                {inflow ? '+' : '−'}${formatAmount(t.amount_value)}
              </span>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
