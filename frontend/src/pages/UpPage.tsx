import { useEffect, useMemo, useState } from 'react'

import AccountList from '../components/up/AccountList'
import TransactionList from '../components/up/TransactionList'
import SpendingDonut from '../components/up/SpendingDonut'
import SyncStatusBanner from '../components/up/SyncStatusBanner'
import RangePicker, { type Range, RANGE_DAYS } from '../components/combined/RangePicker'
import RecurringList from '../components/up/RecurringList'
import { useUpSyncStatus } from '../hooks/useUpSyncStatus'
import {
  fetchAccounts, fetchTransactions, fetchSpendingSummary, fetchRecurring,
} from '../api/up'
import type { UpAccount, UpTransaction, RecurringCharge } from '../types/up'

function rangeSinceIso(range: Range): string {
  const days = RANGE_DAYS[range]
  if (days === null) {
    return new Date('2020-01-01T00:00:00Z').toISOString()
  }
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - days)
  d.setUTCHours(0, 0, 0, 0)
  return d.toISOString()
}

const RANGE_LABELS: Record<Range, string> = {
  '1W': 'last 7 days',
  '1M': 'last 30 days',
  '3M': 'last 3 months',
  '6M': 'last 6 months',
  '1Y': 'last year',
  ALL: 'all time',
}

function fmt(n: number): string {
  return `$${n.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

function fmtSigned(n: number): string {
  const sign = n < 0 ? '−' : '+'
  return `${sign}$${Math.abs(n).toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

export default function UpPage() {
  const sync = useUpSyncStatus()
  const [accounts, setAccounts] = useState<UpAccount[]>([])
  const [recurring, setRecurring] = useState<RecurringCharge[]>([])
  const [transactions, setTransactions] = useState<UpTransaction[]>([])
  const [spending, setSpending] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [accountsLoading, setAccountsLoading] = useState(true)
  const [recurringLoading, setRecurringLoading] = useState(true)
  const [range, setRange] = useState<Range>('1M')

  const since = useMemo(() => rangeSinceIso(range), [range])
  const until = useMemo(() => new Date().toISOString(), [range])

  useEffect(() => {
    let cancelled = false
    setAccountsLoading(true)
    setRecurringLoading(true)
    Promise.all([
      fetchAccounts(),
      fetchRecurring(),
    ]).then(([a, r]) => {
      if (cancelled) return
      setAccounts(a); setAccountsLoading(false)
      setRecurring(r); setRecurringLoading(false)
    }).catch(() => {
      if (cancelled) return
      setAccountsLoading(false); setRecurringLoading(false)
    })
    return () => { cancelled = true }
  }, [sync?.state])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      fetchTransactions({ limit: 500, since, until }),
      fetchSpendingSummary(since, until),
    ]).then(([t, s]) => {
      if (cancelled) return
      setTransactions(t); setSpending(s); setLoading(false)
    }).catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [since, until, sync?.state])

  const totalCash = useMemo(
    () => accounts.reduce((s, a) => s + a.balance_value, 0),
    [accounts],
  )

  const flow = useMemo(() => {
    let income = 0, expense = 0
    for (const t of transactions) {
      if (t.amount_value >= 0) income += t.amount_value
      else expense += Math.abs(t.amount_value)
    }
    return { income, expense, net: income - expense }
  }, [transactions])

  return (
    <main className="min-h-screen bg-surface text-txt-primary font-sans">
      <div className="max-w-3xl mx-auto px-6">

        {sync && sync.state !== 'ready' && (
          <div className="pt-6">
            <SyncStatusBanner status={sync} />
          </div>
        )}

        {/* Hero — total cash + net flow over range */}
        <header className="pt-10 pb-10">
          <div className="flex items-baseline justify-between gap-4 flex-wrap mb-6">
            <p className="text-sm font-medium text-txt-muted">Total cash</p>
            <RangePicker value={range} onChange={setRange} />
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
                value={`+$${flow.income.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`}
                tone="profit"
              />
              <Stat
                label="Expense"
                value={`−$${flow.expense.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`}
                tone="neutral"
              />
              <Stat
                label="Net"
                value={fmtSigned(flow.net)}
                tone={flow.net >= 0 ? 'profit' : 'loss'}
              />
            </div>
          )}
          {!loading && (
            <p className="mt-2 text-xs font-medium text-txt-muted">
              over {RANGE_LABELS[range]}
            </p>
          )}
        </header>

        {/* Accounts */}
        <Section title="Accounts">
          {accountsLoading ? <Skeleton /> : <AccountList accounts={accounts} />}
        </Section>

        {/* Spending breakdown */}
        <Section title="Spending by category">
          {loading ? <Skeleton tall /> : <SpendingDonut breakdown={spending} />}
        </Section>

        {/* Subscriptions */}
        <Section title="Subscriptions">
          {recurringLoading ? <Skeleton tall /> : <RecurringList charges={recurring} />}
        </Section>

        {/* Transactions */}
        <Section
          title="Transactions"
          aside={
            !loading && transactions.length > 0
              ? `${transactions.length}${transactions.length === 500 ? '+' : ''}`
              : undefined
          }
          last
        >
          {loading ? <Skeleton tall /> : <TransactionList transactions={transactions} />}
        </Section>
      </div>
    </main>
  )
}

function Section({
  title, aside, last, children,
}: {
  title: string
  aside?: string
  last?: boolean
  children: React.ReactNode
}) {
  return (
    <section className={'border-t border-surface-border pt-8 ' + (last ? 'pb-16' : 'pb-10')}>
      <div className="flex items-baseline justify-between gap-4 mb-4">
        <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
          {title}
        </h2>
        {aside && (
          <span className="text-xs font-medium text-txt-muted tabular-nums">{aside}</span>
        )}
      </div>
      {children}
    </section>
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

function Skeleton({ tall }: { tall?: boolean }) {
  return (
    <div className={'animate-pulse-subtle bg-surface-border/50 rounded ' + (tall ? 'h-32' : 'h-12')} />
  )
}
