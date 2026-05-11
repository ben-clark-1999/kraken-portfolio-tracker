import { useEffect, useMemo, useState } from 'react'

import AccountList from '../components/up/AccountList'
import TransactionList from '../components/up/TransactionList'
import SpendingDonut from '../components/up/SpendingDonut'
import SyncStatusBanner from '../components/up/SyncStatusBanner'
import RangePicker, { type Range, RANGE_DAYS } from '../components/combined/RangePicker'
import { useUpSyncStatus } from '../hooks/useUpSyncStatus'
import {
  fetchAccounts, fetchTransactions, fetchSpendingSummary,
} from '../api/up'
import type { UpAccount, UpTransaction } from '../types/up'

function rangeSinceIso(range: Range): string {
  const days = RANGE_DAYS[range]
  if (days === null) {
    // ALL: a very-old anchor; UP hasn't existed before 2020.
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

export default function UpPage() {
  const sync = useUpSyncStatus()
  const [accounts, setAccounts] = useState<UpAccount[]>([])
  const [transactions, setTransactions] = useState<UpTransaction[]>([])
  const [spending, setSpending] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [range, setRange] = useState<Range>('1M')

  const since = useMemo(() => rangeSinceIso(range), [range])
  const until = useMemo(() => new Date().toISOString(), [range])

  // Accounts are independent of range — fetched once per sync transition.
  useEffect(() => {
    let cancelled = false
    fetchAccounts().then(a => { if (!cancelled) setAccounts(a) }).catch(() => {})
    return () => { cancelled = true }
  }, [sync?.state])

  // Spending + transactions react to range AND sync transitions.
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

  return (
    <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <h1 className="text-2xl font-semibold text-txt-primary">UP Bank</h1>
        <RangePicker value={range} onChange={setRange} />
      </div>

      <SyncStatusBanner status={sync} />

      <section><AccountList accounts={accounts} /></section>

      <section>
        <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary mb-3">
          Spending — {RANGE_LABELS[range]}
        </h2>
        {loading ? (
          <div className="text-sm text-txt-muted animate-pulse-subtle">Loading…</div>
        ) : (
          <SpendingDonut breakdown={spending} />
        )}
      </section>

      <section>
        <div className="flex items-baseline justify-between gap-4 mb-3">
          <h2 className="text-sm font-medium uppercase tracking-wider text-txt-secondary">
            Transactions — {RANGE_LABELS[range]}
          </h2>
          {!loading && transactions.length > 0 && (
            <p className="text-xs font-medium text-txt-muted">
              {transactions.length}{transactions.length === 500 ? '+' : ''}
            </p>
          )}
        </div>
        {loading ? (
          <div className="text-sm text-txt-muted animate-pulse-subtle">Loading…</div>
        ) : (
          <TransactionList transactions={transactions} />
        )}
      </section>
    </div>
  )
}
