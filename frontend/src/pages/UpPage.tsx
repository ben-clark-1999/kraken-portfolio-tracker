import { useEffect, useMemo, useState } from 'react'

import SyncStatusBanner from '../components/up/SyncStatusBanner'
import UpTabBar, { useActiveUpTab } from '../components/up/UpTabBar'
import BalanceTab from '../components/up/BalanceTab'
import SpendingTab from '../components/up/SpendingTab'
import TransactionsTab from '../components/up/TransactionsTab'
import AskTab from '../components/up/AskTab'
import { type Range, RANGE_DAYS } from '../components/combined/RangePicker'
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

export default function UpPage() {
  const sync = useUpSyncStatus()
  const { active, setActive } = useActiveUpTab()
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

  // ⌘K / Ctrl+K jumps straight to the Ask AI tab.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setActive('ask')
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [setActive])

  const rangeLabel = RANGE_LABELS[range]

  return (
    <main className="min-h-screen bg-surface text-txt-primary font-sans">
      <div className="w-full max-w-[1440px] mx-auto px-8 pt-6">
        {sync && sync.state !== 'ready' && (
          <div className="pb-4">
            <SyncStatusBanner status={sync} />
          </div>
        )}
        <UpTabBar />
      </div>

      <div className="w-full max-w-[1440px] mx-auto px-8 py-8 animate-rise">
        {active === 'balance' && (
          <BalanceTab
            accounts={accounts}
            transactions={transactions}
            accountsLoading={accountsLoading}
            loading={loading}
            range={range}
            onRangeChange={setRange}
            rangeLabel={rangeLabel}
          />
        )}
        {active === 'spending' && (
          <SpendingTab
            spending={spending}
            recurring={recurring}
            loading={loading}
            recurringLoading={recurringLoading}
            range={range}
            onRangeChange={setRange}
            rangeLabel={rangeLabel}
          />
        )}
        {active === 'transactions' && (
          <TransactionsTab
            transactions={transactions}
            loading={loading}
            range={range}
            onRangeChange={setRange}
            rangeLabel={rangeLabel}
          />
        )}
        {active === 'ask' && <AskTab />}
      </div>
    </main>
  )
}
