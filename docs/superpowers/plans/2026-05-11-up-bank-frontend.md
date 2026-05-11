# UP Bank Integration — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React frontend for UP Bank: sidebar navigation with three routes (`/combined`, `/crypto`, `/up`), powered by the backend endpoints from Plan A.

**Architecture:** Add `react-router-dom`. Restructure `App.tsx` to render an `AppLayout` shell (sidebar + main + chat panel) with three routed pages. Move existing `Dashboard.tsx` → `CryptoPage.tsx` (one rename, minimal changes). Build `CombinedPage` (KPI tiles + 3-line net-worth chart) and `UpPage` (accounts + spending donut + transaction list + sync banner) on top of the live `/api/up/*` and `/api/combined/*` endpoints.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind, recharts (already in deps), react-router-dom (new), the existing `apiFetch` wrapper.

**Companion plan:** `2026-05-11-up-bank-backend.md` (must be executed first — produces the API endpoints this plan consumes).

**Visual treatment:** This plan defines structure and data flow only. After Tasks 9 and 10 (CombinedPage and UpPage) land in their structural form, invoke the `impeccable` skill to do the actual visual treatment (colors, spacing, typography, chart polish, hover/empty/loading states). Per project convention.

---

## Part 1 — Routing foundation

### Task 1: Install react-router-dom

**Files:**
- Modify: `frontend/package.json` (via npm install)

- [ ] **Step 1: Install**

```bash
cd frontend && npm install react-router-dom
```

- [ ] **Step 2: Verify**

```bash
cd frontend && grep '"react-router-dom"' package.json
```
Expected output includes `"react-router-dom": "^7.x.x"` (or whatever the latest is).

- [ ] **Step 3: Commit**

```bash
cd .. # back to repo root
git add frontend/package.json frontend/package-lock.json
git commit -m "deps(frontend): add react-router-dom"
git push
```

---

### Task 2: AppLayout shell + SidebarNav

**Files:**
- Create: `frontend/src/components/AppLayout.tsx`
- Create: `frontend/src/components/SidebarNav.tsx`

- [ ] **Step 1: Write SidebarNav**

Create `frontend/src/components/SidebarNav.tsx`:

```tsx
import { NavLink } from 'react-router-dom'

const links = [
  { to: '/combined', label: 'Combined' },
  { to: '/crypto',   label: 'Crypto' },
  { to: '/up',       label: 'UP Bank' },
]

export default function SidebarNav() {
  return (
    <nav className="flex flex-col gap-1 p-3 w-44 border-r border-neutral-800 h-full">
      {links.map(l => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            `px-3 py-2 rounded text-sm ${
              isActive ? 'bg-blue-600 text-white' : 'text-neutral-300 hover:bg-neutral-800'
            }`
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  )
}
```

- [ ] **Step 2: Write AppLayout**

Create `frontend/src/components/AppLayout.tsx`:

```tsx
import { ReactNode } from 'react'
import SidebarNav from './SidebarNav'

interface Props {
  children: ReactNode
  /** Slot for the agent chat panel — passed in from App.tsx so layout
   *  doesn't own conversation state. */
  chatPanel?: ReactNode
}

export default function AppLayout({ children, chatPanel }: Props) {
  return (
    <div className="flex min-h-screen bg-surface text-neutral-100">
      <SidebarNav />
      <main className="flex-1 overflow-auto">{children}</main>
      {chatPanel && (
        <aside className="w-96 border-l border-neutral-800">{chatPanel}</aside>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. (If `bg-surface` isn't in tailwind.config.js, swap to a stock class like `bg-neutral-950`.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AppLayout.tsx frontend/src/components/SidebarNav.tsx
git commit -m "feat(frontend): AppLayout + SidebarNav components"
git push
```

---

### Task 3: Move Dashboard.tsx → CryptoPage.tsx + restructure App.tsx with router

**Files:**
- Rename: `frontend/src/pages/Dashboard.tsx` → `frontend/src/pages/CryptoPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Inspect the existing Dashboard.tsx props**

```bash
cd /Users/benclark/Desktop/kraken-portfolio-tracker
grep -n "Dashboard\|interface" frontend/src/pages/Dashboard.tsx | head -20
```

The current `Dashboard` accepts `onSignedOut` as a prop. Note this — `CryptoPage` may keep or drop it depending on where the SignOutButton ends up moving.

- [ ] **Step 2: Rename file and component**

```bash
git mv frontend/src/pages/Dashboard.tsx frontend/src/pages/CryptoPage.tsx
```

Open `CryptoPage.tsx` and rename the default-exported component `Dashboard` → `CryptoPage`. Keep all the existing props/markup intact for now — the agent chat panel may stay inside `CryptoPage` for this task; we'll lift it out in Task 4 if the page renders the chat. (If `CryptoPage` does NOT render the chat — it's already a separate component — leave it.)

- [ ] **Step 3: Restructure App.tsx**

Replace `frontend/src/App.tsx` with:

```tsx
import { useEffect, useState, useCallback } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { UNAUTHORIZED_EVENT } from './api/client'
import { me } from './api/auth'
import AppLayout from './components/AppLayout'
import CryptoPage from './pages/CryptoPage'
import Login from './pages/Login'

type AuthState = 'checking' | 'authenticated' | 'unauthenticated'

export default function App() {
  const [auth, setAuth] = useState<AuthState>('checking')

  const refreshAuth = useCallback(async () => {
    try {
      const ok = await me()
      setAuth(ok ? 'authenticated' : 'unauthenticated')
    } catch {
      setAuth('unauthenticated')
    }
  }, [])

  useEffect(() => { refreshAuth() }, [refreshAuth])

  useEffect(() => {
    function handleUnauthorized() { setAuth('unauthenticated') }
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
  }, [])

  if (auth === 'checking') return <div className="min-h-screen bg-surface" />

  if (auth === 'unauthenticated') {
    return <Login onAuthenticated={() => setAuth('authenticated')} />
  }

  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<Navigate to="/crypto" replace />} />
          <Route path="/crypto" element={<CryptoPage onSignedOut={() => setAuth('unauthenticated')} />} />
          <Route path="/combined" element={<div className="p-6 text-neutral-400">Combined view — coming in Task 9</div>} />
          <Route path="/up" element={<div className="p-6 text-neutral-400">UP Bank view — coming in Task 10</div>} />
          <Route path="*" element={<Navigate to="/crypto" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}
```

(We default-redirect to `/crypto` until `CombinedPage` lands in Task 9 — keeps the app fully functional throughout the build-out.)

- [ ] **Step 4: Manual smoke**

```bash
cd frontend && npm run dev
```
Open http://localhost:5173 in browser. Confirm:
- Sidebar visible with 3 links
- Default lands on `/crypto` and the existing dashboard renders
- `/combined` and `/up` show placeholder text
- Browser back/forward works between routes

If the layout breaks (e.g. dashboard internal layout assumed full-width), capture what's wrong and report DONE_WITH_CONCERNS — we'll iterate.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/CryptoPage.tsx
git commit -m "feat(frontend): router + AppLayout shell, Dashboard→CryptoPage"
git push
```

---

## Part 2 — API + hooks

### Task 4: api/up.ts and api/combined.ts

**Files:**
- Create: `frontend/src/api/up.ts`
- Create: `frontend/src/api/combined.ts`
- Create: `frontend/src/types/up.ts` (shared types)

- [ ] **Step 1: Write types**

Create `frontend/src/types/up.ts`:

```typescript
export interface UpAccount {
  id: string
  display_name: string
  account_type: 'TRANSACTIONAL' | 'SAVER' | 'HOME_LOAN'
  ownership_type: 'INDIVIDUAL' | 'JOINT'
  balance_value: number
  balance_currency: string
  created_at: string
}

export interface UpTransaction {
  id: string
  account_id: string
  status: 'HELD' | 'SETTLED'
  description: string
  message: string | null
  raw_text: string | null
  amount_value: number
  amount_currency: string
  category_id: string | null
  parent_category_id: string | null
  created_at: string
  settled_at: string | null
}

export interface CashflowRow {
  period: string
  income: number
  expense: number
}

export interface SyncStatus {
  state: 'ready' | 'syncing' | 'error'
  last_synced_at: string | null
  error: string | null
}

export interface CombinedSnapshot {
  captured_at: string
  crypto: number
  up: number
  total: number
}

export interface CombinedSummary {
  crypto: number
  up: number
  total: number
}
```

- [ ] **Step 2: Write api/up.ts**

Create `frontend/src/api/up.ts`:

```typescript
import { apiFetch } from './client'
import type {
  UpAccount, UpTransaction, CashflowRow, SyncStatus,
} from '../types/up'

export async function fetchAccounts(): Promise<UpAccount[]> {
  const r = await apiFetch('/api/up/accounts')
  if (!r.ok) throw new Error(`accounts: ${r.status}`)
  return r.json()
}

export async function fetchTransactions(opts?: {
  limit?: number; since?: string; until?: string;
}): Promise<UpTransaction[]> {
  const params = new URLSearchParams()
  if (opts?.limit) params.set('limit', String(opts.limit))
  if (opts?.since) params.set('since', opts.since)
  if (opts?.until) params.set('until', opts.until)
  const url = `/api/up/transactions${params.size ? `?${params}` : ''}`
  const r = await apiFetch(url)
  if (!r.ok) throw new Error(`transactions: ${r.status}`)
  return r.json()
}

export async function fetchSpendingSummary(
  since: string, until: string,
): Promise<Record<string, number>> {
  const r = await apiFetch(`/api/up/spending/summary?since=${encodeURIComponent(since)}&until=${encodeURIComponent(until)}`)
  if (!r.ok) throw new Error(`spending: ${r.status}`)
  return r.json()
}

export async function fetchCashflow(
  since: string, until: string, granularity: 'day' | 'week' | 'month' = 'month',
): Promise<CashflowRow[]> {
  const r = await apiFetch(`/api/up/cashflow?since=${encodeURIComponent(since)}&until=${encodeURIComponent(until)}&granularity=${granularity}`)
  if (!r.ok) throw new Error(`cashflow: ${r.status}`)
  return r.json()
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const r = await apiFetch('/api/up/sync/status')
  if (!r.ok) throw new Error(`sync status: ${r.status}`)
  return r.json()
}

export async function triggerSyncRetry(): Promise<void> {
  const r = await apiFetch('/api/up/sync/retry', { method: 'POST' })
  if (!r.ok) throw new Error(`retry: ${r.status}`)
}
```

- [ ] **Step 3: Write api/combined.ts**

Create `frontend/src/api/combined.ts`:

```typescript
import { apiFetch } from './client'
import type { CombinedSnapshot, CombinedSummary } from '../types/up'

export async function fetchCombinedSnapshots(since?: string): Promise<CombinedSnapshot[]> {
  const url = since
    ? `/api/combined/snapshots?since=${encodeURIComponent(since)}`
    : '/api/combined/snapshots'
  const r = await apiFetch(url)
  if (!r.ok) throw new Error(`combined snapshots: ${r.status}`)
  return r.json()
}

export async function fetchCombinedSummary(): Promise<CombinedSummary> {
  const r = await apiFetch('/api/combined/summary')
  if (!r.ok) throw new Error(`combined summary: ${r.status}`)
  return r.json()
}
```

- [ ] **Step 4: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/up.ts frontend/src/api/combined.ts frontend/src/types/up.ts
git commit -m "feat(frontend): API clients for UP and combined endpoints"
git push
```

---

### Task 5: useUpSyncStatus polling hook

**Files:**
- Create: `frontend/src/hooks/useUpSyncStatus.ts`
- Test: `frontend/src/hooks/useUpSyncStatus.test.tsx`

- [ ] **Step 1: Write failing test**

Create `frontend/src/hooks/useUpSyncStatus.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useUpSyncStatus } from './useUpSyncStatus'
import * as upApi from '../api/up'

describe('useUpSyncStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('polls every 10s while state is syncing, stops once ready', async () => {
    const spy = vi.spyOn(upApi, 'fetchSyncStatus')
      .mockResolvedValueOnce({ state: 'syncing', last_synced_at: null, error: null })
      .mockResolvedValueOnce({ state: 'syncing', last_synced_at: null, error: null })
      .mockResolvedValueOnce({ state: 'ready', last_synced_at: '2026-05-11T00:00:00Z', error: null })

    const { result } = renderHook(() => useUpSyncStatus())

    await waitFor(() => expect(result.current?.state).toBe('syncing'))
    expect(spy).toHaveBeenCalledTimes(1)

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    expect(spy).toHaveBeenCalledTimes(2)

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    await waitFor(() => expect(result.current?.state).toBe('ready'))
    expect(spy).toHaveBeenCalledTimes(3)

    // Once ready, polling stops — advancing further should NOT increment
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
    expect(spy).toHaveBeenCalledTimes(3)
  })
})
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd frontend && npx vitest run src/hooks/useUpSyncStatus.test.tsx
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useUpSyncStatus.ts`:

```typescript
import { useEffect, useState, useRef } from 'react'
import { fetchSyncStatus } from '../api/up'
import type { SyncStatus } from '../types/up'

const POLL_INTERVAL_MS = 10_000

export function useUpSyncStatus() {
  const [status, setStatus] = useState<SyncStatus | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    cancelledRef.current = false
    let timer: ReturnType<typeof setTimeout> | null = null

    async function poll() {
      try {
        const s = await fetchSyncStatus()
        if (cancelledRef.current) return
        setStatus(s)
        if (s.state === 'syncing') {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        // silent — banner stays in last known state
      }
    }

    poll()

    return () => {
      cancelledRef.current = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  return status
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/hooks/useUpSyncStatus.test.tsx
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useUpSyncStatus.ts frontend/src/hooks/useUpSyncStatus.test.tsx
git commit -m "feat(frontend): useUpSyncStatus polling hook"
git push
```

---

## Part 3 — UP Bank page

### Task 6: SyncStatusBanner component

**Files:**
- Create: `frontend/src/components/up/SyncStatusBanner.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/up/SyncStatusBanner.tsx`:

```tsx
import type { SyncStatus } from '../../types/up'
import { triggerSyncRetry } from '../../api/up'

interface Props {
  status: SyncStatus | null
}

export default function SyncStatusBanner({ status }: Props) {
  if (!status) return null
  if (status.state === 'ready') return null

  if (status.state === 'syncing') {
    return (
      <div className="p-3 bg-blue-900/40 border border-blue-700 rounded text-sm text-blue-100">
        Syncing your UP Bank history… data appears as it streams in.
      </div>
    )
  }

  // error
  return (
    <div className="p-3 bg-red-900/40 border border-red-700 rounded text-sm text-red-100 flex items-center justify-between">
      <span>UP sync failed: {status.error ?? 'unknown error'}</span>
      <button
        onClick={() => triggerSyncRetry()}
        className="ml-3 px-3 py-1 bg-red-700 hover:bg-red-600 rounded text-xs"
      >
        Retry
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Verify TS**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/up/SyncStatusBanner.tsx
git commit -m "feat(frontend): SyncStatusBanner component"
git push
```

---

### Task 7: AccountList + TransactionList + SpendingDonut components

**Files:**
- Create: `frontend/src/components/up/AccountList.tsx`
- Create: `frontend/src/components/up/TransactionList.tsx`
- Create: `frontend/src/components/up/SpendingDonut.tsx`

- [ ] **Step 1: AccountList**

Create `frontend/src/components/up/AccountList.tsx`:

```tsx
import type { UpAccount } from '../../types/up'

interface Props { accounts: UpAccount[] }

export default function AccountList({ accounts }: Props) {
  if (accounts.length === 0) {
    return <div className="text-sm text-neutral-500">No accounts yet.</div>
  }
  const total = accounts.reduce((s, a) => s + a.balance_value, 0)
  return (
    <div>
      <div className="text-sm text-neutral-400 mb-1">Total cash</div>
      <div className="text-3xl font-semibold mb-4">${total.toLocaleString('en-AU', { minimumFractionDigits: 2 })}</div>
      <div className="space-y-1">
        {accounts.sort((a, b) => b.balance_value - a.balance_value).map(a => (
          <div key={a.id} className="flex justify-between py-2 border-b border-neutral-800">
            <div>
              <div className="text-sm">{a.display_name}</div>
              <div className="text-xs text-neutral-500">{a.account_type}</div>
            </div>
            <div className="font-mono text-sm">${a.balance_value.toLocaleString('en-AU', { minimumFractionDigits: 2 })}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TransactionList**

Create `frontend/src/components/up/TransactionList.tsx`:

```tsx
import type { UpTransaction } from '../../types/up'

interface Props { transactions: UpTransaction[] }

export default function TransactionList({ transactions }: Props) {
  if (transactions.length === 0) {
    return <div className="text-sm text-neutral-500">No transactions in range.</div>
  }
  return (
    <ul className="divide-y divide-neutral-800">
      {transactions.map(t => (
        <li key={t.id} className="flex justify-between py-2">
          <div>
            <div className="text-sm">{t.description}</div>
            <div className="text-xs text-neutral-500">{t.created_at.slice(0, 10)} · {t.status}</div>
          </div>
          <div className={`font-mono text-sm ${t.amount_value < 0 ? 'text-red-300' : 'text-green-300'}`}>
            {t.amount_value < 0 ? '-' : '+'}${Math.abs(t.amount_value).toLocaleString('en-AU', { minimumFractionDigits: 2 })}
          </div>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 3: SpendingDonut**

Create `frontend/src/components/up/SpendingDonut.tsx`:

```tsx
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

interface Props {
  /** Map of category → AUD spend */
  breakdown: Record<string, number>
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4', '#84cc16']

export default function SpendingDonut({ breakdown }: Props) {
  const data = Object.entries(breakdown)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)

  if (data.length === 0) {
    return <div className="text-sm text-neutral-500">No spending in range.</div>
  }

  const total = data.reduce((s, d) => s + d.value, 0)

  return (
    <div className="flex items-center gap-6">
      <div className="w-40 h-40">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="value" innerRadius={45} outerRadius={75}>
              {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v: number) => `$${v.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex-1 text-sm">
        <div className="text-neutral-400 mb-2">Total: ${total.toLocaleString('en-AU', { minimumFractionDigits: 2 })}</div>
        <ul className="space-y-1">
          {data.map((d, i) => (
            <li key={d.name} className="flex justify-between">
              <span className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
                {d.name}
              </span>
              <span className="font-mono">${d.value.toLocaleString('en-AU', { minimumFractionDigits: 2 })}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Verify TS compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/up/AccountList.tsx frontend/src/components/up/TransactionList.tsx frontend/src/components/up/SpendingDonut.tsx
git commit -m "feat(frontend): AccountList + TransactionList + SpendingDonut components"
git push
```

---

### Task 8: UpPage

**Files:**
- Create: `frontend/src/pages/UpPage.tsx`
- Modify: `frontend/src/App.tsx` (replace placeholder route)

- [ ] **Step 1: Write the page**

Create `frontend/src/pages/UpPage.tsx`:

```tsx
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
    // Re-fetch when sync transitions to ready (data freshly written)
  }, [sync?.state])

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <h1 className="text-2xl font-semibold">UP Bank</h1>
      <SyncStatusBanner status={sync} />

      {loading ? (
        <div className="text-sm text-neutral-500">Loading…</div>
      ) : (
        <>
          <section><AccountList accounts={accounts} /></section>

          <section>
            <h2 className="text-sm uppercase text-neutral-400 mb-3">Spending this month</h2>
            <SpendingDonut breakdown={spending} />
          </section>

          <section>
            <h2 className="text-sm uppercase text-neutral-400 mb-3">Recent transactions</h2>
            <TransactionList transactions={transactions} />
          </section>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Wire route in App.tsx**

In `frontend/src/App.tsx`, replace the `/up` placeholder route:

```tsx
import UpPage from './pages/UpPage'
// ... and replace the route definition:
<Route path="/up" element={<UpPage />} />
```

- [ ] **Step 3: Verify TS compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Manual smoke**

Open http://localhost:5173/up. Confirm:
- Sync banner appears if sync is in progress (or nothing if ready)
- Account balances load and total displays
- Spending donut renders with categories
- Recent transactions list shows entries

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/UpPage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): UpPage — accounts, spending donut, transactions"
git push
```

---

## Part 4 — Combined view

### Task 9: KpiTiles + NetWorthChart + CombinedPage

**Files:**
- Create: `frontend/src/components/combined/KpiTiles.tsx`
- Create: `frontend/src/components/combined/NetWorthChart.tsx`
- Create: `frontend/src/pages/CombinedPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: KpiTiles**

Create `frontend/src/components/combined/KpiTiles.tsx`:

```tsx
import type { CombinedSummary } from '../../types/up'

interface Props { summary: CombinedSummary | null }

function fmt(n: number): string {
  return `$${n.toLocaleString('en-AU', { minimumFractionDigits: 2 })}`
}

export default function KpiTiles({ summary }: Props) {
  if (!summary) {
    return <div className="grid grid-cols-3 gap-4">
      {['Combined', 'Crypto', 'UP cash'].map(l => (
        <div key={l} className="p-4 bg-neutral-900 rounded">
          <div className="text-xs uppercase text-neutral-500">{l}</div>
          <div className="text-xl font-mono text-neutral-700">—</div>
        </div>
      ))}
    </div>
  }
  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="p-4 bg-neutral-900 rounded">
        <div className="text-xs uppercase text-neutral-400">Combined</div>
        <div className="text-2xl font-mono">{fmt(summary.total)}</div>
      </div>
      <div className="p-4 bg-neutral-900 rounded">
        <div className="text-xs uppercase text-neutral-400">Crypto</div>
        <div className="text-2xl font-mono">{fmt(summary.crypto)}</div>
      </div>
      <div className="p-4 bg-neutral-900 rounded">
        <div className="text-xs uppercase text-neutral-400">UP cash</div>
        <div className="text-2xl font-mono">{fmt(summary.up)}</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: NetWorthChart (3 overlaid lines)**

Create `frontend/src/components/combined/NetWorthChart.tsx`:

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts'
import type { CombinedSnapshot } from '../../types/up'

interface Props { snapshots: CombinedSnapshot[] }

export default function NetWorthChart({ snapshots }: Props) {
  if (snapshots.length === 0) {
    return <div className="h-72 flex items-center justify-center text-sm text-neutral-500">
      No snapshot history yet.
    </div>
  }

  const data = snapshots.map(s => ({
    time: s.captured_at.slice(0, 10),
    Total: Math.round(s.total),
    Crypto: Math.round(s.crypto),
    UP: Math.round(s.up),
  }))

  return (
    <div className="h-72">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="time" stroke="#6b7280" fontSize={11} />
          <YAxis stroke="#6b7280" fontSize={11} tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
          <Tooltip
            contentStyle={{ background: '#0a0a0a', border: '1px solid #374151', fontSize: 12 }}
            formatter={(v: number) => `$${v.toLocaleString('en-AU')}`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="Total" stroke="#a855f7" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="Crypto" stroke="#3b82f6" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="UP" stroke="#10b981" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 3: CombinedPage**

Create `frontend/src/pages/CombinedPage.tsx`:

```tsx
import { useEffect, useState } from 'react'

import KpiTiles from '../components/combined/KpiTiles'
import NetWorthChart from '../components/combined/NetWorthChart'
import SyncStatusBanner from '../components/up/SyncStatusBanner'
import { useUpSyncStatus } from '../hooks/useUpSyncStatus'
import { fetchCombinedSummary, fetchCombinedSnapshots } from '../api/combined'
import type { CombinedSummary, CombinedSnapshot } from '../types/up'

export default function CombinedPage() {
  const sync = useUpSyncStatus()
  const [summary, setSummary] = useState<CombinedSummary | null>(null)
  const [snapshots, setSnapshots] = useState<CombinedSnapshot[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchCombinedSummary(),
      fetchCombinedSnapshots(), // all-time
    ]).then(([s, snaps]) => {
      if (cancelled) return
      setSummary(s); setSnapshots(snaps); setLoading(false)
    }).catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [sync?.state])

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <h1 className="text-2xl font-semibold">Combined Net Worth</h1>
      <SyncStatusBanner status={sync} />
      {loading ? (
        <div className="text-sm text-neutral-500">Loading…</div>
      ) : (
        <>
          <KpiTiles summary={summary} />
          <section>
            <h2 className="text-sm uppercase text-neutral-400 mb-3">Net worth over time</h2>
            <NetWorthChart snapshots={snapshots} />
          </section>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Wire route + change default redirect to /combined**

In `frontend/src/App.tsx`:
- Add `import CombinedPage from './pages/CombinedPage'`
- Replace the `/combined` placeholder with `<Route path="/combined" element={<CombinedPage />} />`
- Update the `/` and `*` redirects to point to `/combined` (now that it exists, that's the new home)

- [ ] **Step 5: Verify TS compiles**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Manual smoke**

Open http://localhost:5173/. Should land on `/combined`. Confirm:
- 3 KPI tiles show numbers
- Chart renders with 3 lines (Total, Crypto, UP)
- Sync banner shows if syncing

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/combined/KpiTiles.tsx frontend/src/components/combined/NetWorthChart.tsx frontend/src/pages/CombinedPage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): CombinedPage with KPI tiles + 3-line chart"
git push
```

---

## Part 5 — Polish & verification

### Task 10: Visual polish via /impeccable

**Files:**
- Variable — depends on what `impeccable` recommends.

- [ ] **Step 1: Invoke /impeccable on the new pages**

Run `/impeccable` on `CombinedPage` and `UpPage`. Per the project memory, frontend tasks in this project use `/impeccable` rather than raw Tailwind for visual polish. The skill will inspect the rendered pages and propose targeted changes (typography, spacing, color palette, hover/empty/loading states).

Apply the recommended changes one component at a time, committing each.

- [ ] **Step 2: Final smoke after polish**

Visit each route, exercise empty/loading/error states (e.g. by stopping uvicorn briefly to see error banners; by hitting `/api/up/sync/retry` to see "syncing" state).

- [ ] **Step 3: Commit any polish changes**

```bash
git add frontend/src/components/ frontend/src/pages/
git commit -m "polish(frontend): /impeccable pass on UP + Combined pages"
git push
```

---

### Task 11: End-to-end smoke

**Files:** none

- [ ] **Step 1: Verify both servers are running**

```bash
lsof -iTCP:8000 -sTCP:LISTEN | head -2
lsof -iTCP:5173 -sTCP:LISTEN | head -2
```

Both should show a listening process. If not, start them.

- [ ] **Step 2: Browser walkthrough**

1. Open http://localhost:5173 — should redirect to `/combined` and show KPI tiles + chart.
2. Click "UP Bank" in sidebar — accounts, donut, transactions all render.
3. Click "Crypto" — existing dashboard renders unchanged.
4. Click "Combined" — back to combined view, state preserved.
5. Open the agent chat (if visible in `AppLayout`) and ask: "How much cash do I have?" — agent should route to `cash_agent` and respond using `get_up_balance`.

- [ ] **Step 3: Network tab sanity check**

DevTools → Network. Filter to `/api`. Confirm:
- `/api/combined/summary` returns 200 with `{crypto, up, total}`
- `/api/combined/snapshots` returns 200 with array
- `/api/up/accounts` returns 200 with array
- `/api/up/transactions?limit=50` returns 200 with array
- `/api/up/spending/summary?since=...&until=...` returns 200 with object
- `/api/up/sync/status` returns 200 with `{state, last_synced_at, error}`

- [ ] **Step 4: No commit unless bugs found**

If any bug surfaces, fix and commit with `fix(frontend): ...`.

---

## Spec coverage check

| Spec section | Implemented in |
|---|---|
| Routing (BrowserRouter + 3 routes) | Task 3 |
| AppLayout shell | Task 2 |
| SidebarNav | Task 2 |
| CombinedPage | Task 9 |
| CryptoPage (renamed Dashboard) | Task 3 |
| UpPage | Task 8 |
| AccountList | Task 7 |
| SpendingDonut | Task 7 |
| TransactionList | Task 7 |
| SyncStatusBanner | Task 6 |
| NetWorthChart | Task 9 |
| KpiTiles | Task 9 |
| api/up.ts | Task 4 |
| api/combined.ts | Task 4 |
| useUpSyncStatus | Task 5 |
| Loading/empty states | Tasks 7, 8, 9 |
| Sync error retry | Task 6 |
| Visual polish (impeccable) | Task 10 |
| Cross-route chat panel | Task 2 (AppLayout has slot; left empty for now — wire when an existing AgentPanel is lifted out of CryptoPage) |

All frontend spec requirements covered.

---

## Open follow-ups (not in this plan)

- **Lifting the agent chat panel out of CryptoPage** so it lives in `AppLayout` and stays present across routes. This was deferred to keep this plan tightly scoped — Task 2's `AppLayout` accepts a `chatPanel` slot but `App.tsx` doesn't pass one yet. If the user wants the chat across all routes, this is a small follow-up.
- **Mobile responsive sidebar** — current sidebar is fixed-width. Should collapse / become a hamburger on narrow viewports. Out of scope.

---

## Execution

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between, fast iteration.

**2. Inline Execution** — batch execution with checkpoints.

Which approach?
