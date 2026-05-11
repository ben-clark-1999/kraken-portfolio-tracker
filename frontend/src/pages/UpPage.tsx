import { useEffect, useState } from 'react'

import AccountList from '../components/up/AccountList'
import TransactionList from '../components/up/TransactionList'
import SpendingDonut from '../components/up/SpendingDonut'
import SyncStatusBanner from '../components/up/SyncStatusBanner'
import { useUpSyncStatus } from '../hooks/useUpSyncStatus'
import {
  fetchAccounts, fetchTransactions, fetchSpendingSummary,
} from '../api/up'
import type { UpAccount, UpTransaction } from '../types/up'

function startOfMonthIso(): string {
  const d = new Date()
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)).toISOString()
}

function nowIso(): string {
  return new Date().toISOString()
}

export default function UpPage() {
  const sync = useUpSyncStatus()
  const [accounts, setAccounts] = useState<UpAccount[]>([])
  const [transactions, setTransactions] = useState<UpTransaction[]>([])
  const [spending, setSpending] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchAccounts(),
      fetchTransactions({ limit: 50 }),
      fetchSpendingSummary(startOfMonthIso(), nowIso()),
    ]).then(([a, t, s]) => {
      if (cancelled) return
      setAccounts(a); setTransactions(t); setSpending(s); setLoading(false)
    }).catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // Re-fetch when sync transitions (data freshly written)
  }, [sync?.state])

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
      <h1 className="text-2xl font-semibold text-txt-primary">UP Bank</h1>
      <SyncStatusBanner status={sync} />

      {loading ? (
        <div className="text-sm text-txt-muted">Loading…</div>
      ) : (
        <>
          <section><AccountList accounts={accounts} /></section>

          <section>
            <h2 className="text-sm uppercase text-txt-secondary mb-3">Spending this month</h2>
            <SpendingDonut breakdown={spending} />
          </section>

          <section>
            <h2 className="text-sm uppercase text-txt-secondary mb-3">Recent transactions</h2>
            <TransactionList transactions={transactions} />
          </section>
        </>
      )}
    </div>
  )
}
