# Crypto Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-scroll `/crypto` page with four focused tabs (Balance, Asset Breakdown, Previous Purchases, Ask AI), give the LangGraph chat a real conversational surface, fix markdown rendering so tables and other constructs render correctly, and add a manual Sync-now button so new Kraken purchases appear without restarting.

**Architecture:** `CryptoPage` becomes a thin host owning a single `useCryptoData` hook and a tab router driven by a URL search-param. Each tab is a small component that pulls only the data slice it needs. The Ask AI tab owns `useAgentChat` and renders either a hero empty-state or a standard chat conversation depending on `messages.length`. Markdown rendering is upgraded with `remark-gfm` and a full component-map. Anti-slop discipline is enforced by routing visual work through the installed `redesign-existing-projects` → `/impeccable craft` → `design-taste-frontend` (discipline only) → `/critique` → `/polish` chain.

**Tech Stack:** React 18 + Vite + TypeScript, Tailwind (existing tokens: `kraken`, `accent`, `surface-{raised,border}`, `txt-{primary,secondary,muted}`), Vitest + @testing-library/react, `react-markdown` v10 + `remark-gfm` (new). Backend: existing `POST /api/sync` and `GET /api/history/trades` endpoints — no backend code changes.

**Design read (declared up front, per `design-taste-frontend` §0.B):**
*"Reading this as: an existing data-rich crypto portfolio dashboard for a single technical user, with a Linear-style restrained product language, leaning toward the project's existing dark surface tokens + kraken-purple accent + accent-teal highlight. Dials: VARIANCE 5, MOTION 4, DENSITY 5 (dashboard preset, not landing-page maximal)."*

---

## File map

### New files
- `frontend/src/hooks/useCryptoData.ts` — extracts current `CryptoPage.refresh` logic.
- `frontend/src/hooks/useCryptoData.test.tsx` — covers fetch success / partial failure / refresh.
- `frontend/src/components/crypto/CryptoTabBar.tsx` — underline tab bar bound to `?tab=` search-param.
- `frontend/src/components/crypto/CryptoTabBar.test.tsx`
- `frontend/src/components/crypto/BalanceTab.tsx`
- `frontend/src/components/crypto/AssetsTab.tsx`
- `frontend/src/components/crypto/PurchasesTab.tsx`
- `frontend/src/components/crypto/PurchasesTab.test.tsx`
- `frontend/src/components/crypto/AskTab.tsx`
- `frontend/src/components/crypto/AskTab.test.tsx`
- `frontend/src/components/AgentConversation.tsx`
- `frontend/src/components/SuggestionPills.tsx`

### Modified files
- `frontend/package.json` — add `remark-gfm@4`.
- `frontend/src/pages/CryptoPage.tsx` — collapse to tab router + sign-out.
- `frontend/src/components/AgentMessage.tsx` — add `remarkPlugins={[remarkGfm]}` and full component map; keep existing string-coercion guard.
- `frontend/src/components/AgentMessage.test.tsx` (new file, but co-located with the component) — verify table / heading / list / code render.
- `frontend/src/components/AgentInput.tsx` — accept `variant?: 'hero' | 'docked'` prop.
- `frontend/src/components/DCAHistoryTable.tsx` — drop `Current Value` and `P&L` columns, swap `bg-gray-*` for theme tokens, drop the inline `<h2>DCA History</h2>` heading (the tab title carries the label).

---

## Task 0: Anti-slop pre-implementation audit

**Files:** none (output to chat / temporary scratch only)

- [ ] **Step 1: Run the `redesign-existing-projects` audit on the current `/crypto` page**

Invoke the `redesign-existing-projects` skill and read its audit checklist. Walk the current page (`frontend/src/pages/CryptoPage.tsx` + the components it composes) against each section (Typography / Colour and Surfaces / Layout / Interactivity and States / Content) and list every weak point you find.

- [ ] **Step 2: Record findings inline in this plan**

Edit this file and write a short bulleted list under the heading **"Audit findings"** below this task — one bullet per issue, with the file:line where applicable. Keep it terse; this is reconnaissance, not prose.

### Audit findings

Walked the current `/crypto` page (`CryptoPage.tsx` + composed components) against the `redesign-existing-projects` checklist. Findings ordered by severity for this redesign:

**P0 — already addressed in the spec:**
- Markdown tables emitted by the agent fail to render — `react-markdown` is loaded without `remark-gfm`. Visible as raw `| Asset | Qty | …|` pipe text in the right rail. Fixed by Task 2.
- Right-rail `AgentPanel` (`w-96` ≈ 384px) is the direct cause of the cramped chat. Fixed by promoting AI chat to its own full-width tab (Tasks 11, 12).
- `DCAHistoryTable` has no empty state — renders an empty `<tbody>` when entries are zero. Fixed by Task 7 (`PurchasesTab` empty placeholder).

**P1 — to apply during implementation:**
- **Tabular-nums inconsistency.** Big balance ($6,131.63), DCA table costs, and chart axis labels should all use `tabular-nums`. Task 6 (new `DCAHistoryTable`) and Task 11 (AskTab table styling via the markdown `td` component) already include this; double-check `ChartCard`'s axis labels look right.
- **Two accent colors active** (kraken purple + accent teal). Per the audit, "pick one." Justified exception here because the teal is the data-line colour on the chart and the purple is brand/action — they don't compete for hierarchy. Keep both; do not introduce a third accent.

**P2 — out of scope but worth noting:**
- **Default browser font stack.** No custom font is loaded; the project uses Tailwind's `font-sans` (system stack). Geist or similar would lift premium-ness across the whole app — but adding it touches every page. Defer to a separate decision after this redesign ships.
- **Existing `ChartCard` range toggle (`1W/1M/3M/1Y/ALL`) buttons lack a visible focus ring.** Out of scope (this redesign doesn't touch ChartCard). Note for a future polish pass.
- **Tinted shadows on cards.** Current cards use border-only, no shadow. Border-only works for this dashboard; not a problem. Could add subtle inset highlights later if cards start to feel flat.

**Anti-patterns banned for this redesign (declared up-front):**
- AI-purple gradient mesh as background decoration. The new AskTab backdrop blurs use kraken (`bg-kraken/30`) and accent (`bg-accent/20`) tokens at `opacity-30 blur-3xl` — not the generic AI-blue gradient slab.
- Centered hero over dark mesh on every empty state. The AskTab hero is the only hero on the page; other tabs are content-first.
- Three-equal-card feature rows. Not used here.
- Inter + slate-900. Not used.
- Instant transitions. All interactive elements get `duration-200` or longer.

- [ ] **Step 3: Commit the audit**

```bash
git add docs/superpowers/plans/2026-05-26-crypto-page-redesign.md
git commit -m "docs(plan): record anti-slop audit findings for /crypto"
git push
```

---

## Task 1: Install `remark-gfm`

**Files:** Modify: `frontend/package.json`, `frontend/package-lock.json`

- [ ] **Step 1: Install the package**

Run from the repo root:

```bash
cd frontend && npm install remark-gfm@^4
```

Expected: `package.json` gains `"remark-gfm": "^4.x.x"` under `dependencies`; lockfile updates.

- [ ] **Step 2: Verify type-check is still clean**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no output (clean).

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "build(frontend): add remark-gfm for GFM markdown rendering"
git push
```

---

## Task 2: Fix `AgentMessage` markdown rendering

**Files:**
- Modify: `frontend/src/components/AgentMessage.tsx`
- Create: `frontend/src/components/AgentMessage.test.tsx`

- [ ] **Step 1: Write failing render tests**

Create `frontend/src/components/AgentMessage.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import AgentMessage from './AgentMessage'
import type { AgentMessage as AgentMessageType } from '../types/agent'

function assistant(content: string): AgentMessageType {
  return { id: 'a-1', role: 'assistant', content, streaming: false }
}

describe('AgentMessage markdown rendering', () => {
  it('renders pipe-table syntax as a real HTML table', () => {
    const md = [
      '| Asset | Qty | Value |',
      '|-------|-----|-------|',
      '| ETH   | 1.3 | $3,908 |',
    ].join('\n')
    render(<AgentMessage message={assistant(md)} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('Asset')).toBeInTheDocument()
    expect(screen.getByText('1.3')).toBeInTheDocument()
  })

  it('renders **bold** as <strong>', () => {
    render(<AgentMessage message={assistant('hello **world**')} />)
    expect(screen.getByText('world').tagName).toBe('STRONG')
  })

  it('renders headings as the correct tag', () => {
    render(<AgentMessage message={assistant('## Snapshot')} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Snapshot' })).toBeInTheDocument()
  })

  it('renders fenced code blocks inside <pre><code>', () => {
    render(<AgentMessage message={assistant('```\nx=1\n```')} />)
    const code = screen.getByText('x=1')
    expect(code.tagName).toBe('CODE')
    expect(code.closest('pre')).not.toBeNull()
  })

  it('still renders user content as plain text without crashing on non-string', () => {
    const m: AgentMessageType = { id: 'u', role: 'user', content: 'hi', streaming: false }
    render(<AgentMessage message={m} />)
    expect(screen.getByText('hi')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the new tests and verify they fail**

```bash
cd frontend && npx vitest run src/components/AgentMessage.test.tsx
```

Expected: FAIL — the pipe-table test fails because `remark-gfm` is not yet wired up; assistant content currently renders as a single paragraph.

- [ ] **Step 3: Update `AgentMessage.tsx` with `remark-gfm` and the full component map**

Replace the contents of `frontend/src/components/AgentMessage.tsx` with:

```tsx
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AgentMessage as AgentMessageType } from '../types/agent'

interface Props {
  message: AgentMessageType
}

const components = {
  p: (props: any) => (
    <p className="text-[15px] leading-relaxed text-txt-primary my-3 first:mt-0 last:mb-0" {...props} />
  ),
  h1: (props: any) => (
    <h1 className="text-2xl font-semibold text-txt-primary mt-6 mb-2" {...props} />
  ),
  h2: (props: any) => (
    <h2 className="text-xl font-semibold text-txt-primary mt-6 mb-2" {...props} />
  ),
  h3: (props: any) => (
    <h3 className="text-base font-semibold text-txt-primary mt-4 mb-1" {...props} />
  ),
  strong: (props: any) => <strong className="font-semibold text-txt-primary" {...props} />,
  em: (props: any) => <em className="italic text-txt-secondary" {...props} />,
  ul: (props: any) => <ul className="my-3 pl-5 space-y-1 list-disc" {...props} />,
  ol: (props: any) => <ol className="my-3 pl-5 space-y-1 list-decimal" {...props} />,
  li: (props: any) => <li className="text-[15px] leading-relaxed text-txt-primary" {...props} />,
  a: (props: any) => (
    <a className="text-kraken hover:underline" target="_blank" rel="noreferrer" {...props} />
  ),
  blockquote: (props: any) => (
    <blockquote className="border-l-2 border-surface-border pl-3 text-txt-secondary italic my-3" {...props} />
  ),
  hr: () => <hr className="border-surface-border my-4" />,
  code: ({ inline, className, children, ...rest }: any) =>
    inline ? (
      <code
        className="px-1 py-0.5 rounded bg-surface-raised text-[13px] font-mono text-accent"
        {...rest}
      >
        {children}
      </code>
    ) : (
      <code className={`block text-[13px] font-mono text-txt-primary ${className ?? ''}`} {...rest}>
        {children}
      </code>
    ),
  pre: (props: any) => (
    <pre
      className="bg-surface-raised border border-surface-border rounded-md p-3 overflow-x-auto my-3"
      {...props}
    />
  ),
  table: (props: any) => (
    <div className="my-3 rounded-md overflow-hidden border border-surface-border">
      <table className="w-full text-sm font-mono tabular-nums border-collapse" {...props} />
    </div>
  ),
  thead: (props: any) => <thead className="bg-surface-raised" {...props} />,
  th: (props: any) => (
    <th
      className="text-left text-xs uppercase tracking-wider text-txt-muted font-medium px-3 py-2 border-b border-surface-border"
      {...props}
    />
  ),
  tr: (props: any) => <tr className="border-b border-surface-border/60 last:border-b-0" {...props} />,
  td: (props: any) => <td className="text-sm text-txt-primary px-3 py-2 tabular-nums" {...props} />,
}

export default function AgentMessage({ message }: Props) {
  if (message.role === 'user') {
    return (
      <p className="text-xs uppercase tracking-wider text-txt-muted font-medium mb-1">
        You said
        <span className="block normal-case tracking-normal text-[15px] text-txt-secondary mt-1 font-sans">
          {typeof message.content === 'string' ? message.content : ''}
        </span>
      </p>
    )
  }

  return (
    <div className="text-[15px] leading-relaxed text-txt-primary font-sans">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {typeof message.content === 'string' ? message.content : ''}
      </Markdown>
      {message.streaming && (
        <span className="inline-block w-1.5 h-4 bg-txt-muted animate-pulse-subtle ml-0.5 align-text-bottom" />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd frontend && npx vitest run src/components/AgentMessage.test.tsx
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AgentMessage.tsx frontend/src/components/AgentMessage.test.tsx
git commit -m "feat(agent-msg): GFM + full component map for markdown rendering"
git push
```

---

## Task 3: Extract `useCryptoData` hook

**Files:**
- Create: `frontend/src/hooks/useCryptoData.ts`
- Create: `frontend/src/hooks/useCryptoData.test.tsx`

The hook owns the existing `refresh()` logic from `CryptoPage.tsx:65-94`. Behaviour identical; just lifted out.

- [ ] **Step 1: Write failing tests**

Create `frontend/src/hooks/useCryptoData.test.tsx`:

```tsx
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCryptoData } from './useCryptoData'

vi.mock('../api/portfolio', () => ({
  fetchPortfolioSummary: vi.fn(),
  fetchSnapshots: vi.fn(),
  fetchDCAHistory: vi.fn(),
}))

import {
  fetchPortfolioSummary,
  fetchSnapshots,
  fetchDCAHistory,
} from '../api/portfolio'

beforeEach(() => {
  vi.resetAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useCryptoData', () => {
  it('populates state from three successful fetches', async () => {
    ;(fetchPortfolioSummary as any).mockResolvedValue({ total_value_aud: 6000, positions: [] })
    ;(fetchSnapshots as any).mockResolvedValue([{ captured_at: '2026-05-26', total_value_aud: 6000 }])
    ;(fetchDCAHistory as any).mockResolvedValue([])

    const { result } = renderHook(() => useCryptoData())

    await waitFor(() => expect(result.current.summary).not.toBeNull())
    expect(result.current.snapshots).toHaveLength(1)
    expect(result.current.errors).toEqual({})
  })

  it('records per-fetch error without crashing', async () => {
    ;(fetchPortfolioSummary as any).mockRejectedValue(new Error('boom'))
    ;(fetchSnapshots as any).mockResolvedValue([])
    ;(fetchDCAHistory as any).mockResolvedValue([])

    const { result } = renderHook(() => useCryptoData())

    await waitFor(() => expect(result.current.errors.summary).toBe('boom'))
    expect(result.current.summary).toBeNull()
  })

  it('refresh() triggers a refetch', async () => {
    ;(fetchPortfolioSummary as any).mockResolvedValue({ total_value_aud: 1, positions: [] })
    ;(fetchSnapshots as any).mockResolvedValue([])
    ;(fetchDCAHistory as any).mockResolvedValue([])

    const { result } = renderHook(() => useCryptoData())
    await waitFor(() => expect(result.current.summary?.total_value_aud).toBe(1))
    ;(fetchPortfolioSummary as any).mockResolvedValue({ total_value_aud: 2, positions: [] })
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.summary?.total_value_aud).toBe(2)
  })
})
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
cd frontend && npx vitest run src/hooks/useCryptoData.test.tsx
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useCryptoData.ts`:

```ts
import { useCallback, useEffect, useState } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'

export interface CryptoDataErrors {
  summary?: string
  snapshots?: string
  dca?: string
}

export interface CryptoDataState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: CryptoDataErrors
  refreshing: boolean
  refresh: () => Promise<void>
}

function errMsg(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

export function useCryptoData(): CryptoDataState {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([])
  const [dcaHistory, setDcaHistory] = useState<DCAEntry[]>([])
  const [errors, setErrors] = useState<CryptoDataErrors>({})
  const [refreshing, setRefreshing] = useState(false)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const next: CryptoDataErrors = {}
    const [s, sn, d] = await Promise.allSettled([
      fetchPortfolioSummary(),
      fetchSnapshots(),
      fetchDCAHistory(),
    ])
    if (s.status === 'fulfilled') setSummary(s.value)
    else next.summary = errMsg(s.reason)
    if (sn.status === 'fulfilled') setSnapshots(sn.value)
    else next.snapshots = errMsg(sn.reason)
    if (d.status === 'fulfilled') setDcaHistory(d.value)
    else next.dca = errMsg(d.reason)
    setErrors(next)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return { summary, snapshots, dcaHistory, errors, refreshing, refresh }
}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd frontend && npx vitest run src/hooks/useCryptoData.test.tsx
```

Expected: 3 PASS.

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useCryptoData.ts frontend/src/hooks/useCryptoData.test.tsx
git commit -m "refactor(crypto): extract useCryptoData hook from CryptoPage"
git push
```

---

## Task 4: Build `CryptoTabBar` (underline tabs + URL search-param)

**Files:**
- Create: `frontend/src/components/crypto/CryptoTabBar.tsx`
- Create: `frontend/src/components/crypto/CryptoTabBar.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/crypto/CryptoTabBar.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'

import CryptoTabBar, { TAB_IDS, type TabId } from './CryptoTabBar'

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="search">{loc.search}</div>
}

function renderAt(initial = '/crypto') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <CryptoTabBar />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('CryptoTabBar', () => {
  it('renders one tab per known TAB_ID', () => {
    renderAt()
    for (const id of TAB_IDS) {
      expect(screen.getByRole('tab', { name: new RegExp(id.label, 'i') })).toBeInTheDocument()
    }
  })

  it('defaults to Balance when ?tab is missing', () => {
    renderAt('/crypto')
    expect(screen.getByRole('tab', { name: /balance/i })).toHaveAttribute('aria-selected', 'true')
  })

  it('reflects ?tab=ask in the active state', () => {
    renderAt('/crypto?tab=ask')
    expect(screen.getByRole('tab', { name: /ask ai/i })).toHaveAttribute('aria-selected', 'true')
  })

  it('clicking a tab updates ?tab=', () => {
    renderAt('/crypto')
    fireEvent.click(screen.getByRole('tab', { name: /previous purchases/i }))
    expect(screen.getByTestId('search').textContent).toBe('?tab=purchases')
  })

  it('falls back to Balance for an unknown ?tab value', () => {
    renderAt('/crypto?tab=garbage')
    expect(screen.getByRole('tab', { name: /balance/i })).toHaveAttribute('aria-selected', 'true')
  })
})
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
cd frontend && npx vitest run src/components/crypto/CryptoTabBar.test.tsx
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement the tab bar**

Create directory and file:

```bash
mkdir -p frontend/src/components/crypto
```

Create `frontend/src/components/crypto/CryptoTabBar.tsx`:

```tsx
import { useSearchParams } from 'react-router-dom'

export type TabId = { id: string; label: string }

export const TAB_IDS: readonly TabId[] = [
  { id: 'balance', label: 'Balance' },
  { id: 'assets', label: 'Asset Breakdown' },
  { id: 'purchases', label: 'Previous Purchases' },
  { id: 'ask', label: 'Ask AI' },
] as const

const DEFAULT_ID = 'balance'

export function useActiveTab(): { active: string; setActive: (id: string) => void } {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const active = TAB_IDS.some((t) => t.id === raw) ? (raw as string) : DEFAULT_ID
  const setActive = (id: string) => {
    const next = new URLSearchParams(params)
    next.set('tab', id)
    setParams(next, { replace: true })
  }
  return { active, setActive }
}

export default function CryptoTabBar() {
  const { active, setActive } = useActiveTab()
  return (
    <div
      role="tablist"
      aria-label="Crypto sections"
      className="border-b border-surface-border flex items-end gap-6"
    >
      {TAB_IDS.map((t) => {
        const isActive = t.id === active
        return (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={isActive}
            onClick={() => setActive(t.id)}
            className={[
              'relative py-3 text-sm font-medium transition-colors duration-200',
              isActive ? 'text-txt-primary' : 'text-txt-muted hover:text-txt-secondary',
            ].join(' ')}
          >
            {t.label}
            <span
              aria-hidden
              className={[
                'absolute left-0 right-0 -bottom-px h-0.5 rounded-full transition-opacity duration-200',
                isActive ? 'bg-kraken opacity-100' : 'opacity-0',
              ].join(' ')}
            />
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd frontend && npx vitest run src/components/crypto/CryptoTabBar.test.tsx
```

Expected: 5 PASS.

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/crypto/CryptoTabBar.tsx frontend/src/components/crypto/CryptoTabBar.test.tsx
git commit -m "feat(crypto): CryptoTabBar with URL-driven active tab"
git push
```

---

## Task 5: Build `BalanceTab` and `AssetsTab` (move existing content into thin tab shells)

**Files:**
- Create: `frontend/src/components/crypto/BalanceTab.tsx`
- Create: `frontend/src/components/crypto/AssetsTab.tsx`

These tabs are pure props-in / JSX-out. No tests needed — the inner components (`ChartCard`, `AssetBreakdown`) are already tested via their own paths and don't change.

- [ ] **Step 1: Create `BalanceTab.tsx`**

```tsx
import { useMemo, useState } from 'react'
import ChartCard, { type Range } from '../ChartCard'
import type { PortfolioSummary, PortfolioSnapshot } from '../../types'

const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
  ALL: null,
}

function filterByRange(snaps: PortfolioSnapshot[], range: Range) {
  const days = RANGE_DAYS[range]
  if (days === null) return snaps
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snaps.filter((s) => new Date(s.captured_at) >= cutoff)
}

interface Props {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  refreshing: boolean
  onRefresh: () => void
  summaryError?: string
  snapshotsError?: string
}

export default function BalanceTab(props: Props) {
  const [range, setRange] = useState<Range>('1M')
  const [view, setView] = useState<'total' | 'per-asset'>('total')
  const filtered = useMemo(() => filterByRange(props.snapshots, range), [props.snapshots, range])
  return (
    <ChartCard
      summary={props.summary}
      snapshots={filtered}
      range={range}
      onRangeChange={setRange}
      view={view}
      onViewChange={setView}
      onRefresh={props.onRefresh}
      refreshing={props.refreshing}
      summaryError={props.summaryError}
      snapshotsError={props.snapshotsError}
    />
  )
}
```

- [ ] **Step 2: Create `AssetsTab.tsx`**

```tsx
import { useMemo, useState } from 'react'
import AssetBreakdown from '../AssetBreakdown'
import type { PortfolioSummary, PortfolioSnapshot } from '../../types'
import type { Range } from '../ChartCard'

const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
  ALL: null,
}

function filterByRange(snaps: PortfolioSnapshot[], range: Range) {
  const days = RANGE_DAYS[range]
  if (days === null) return snaps
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snaps.filter((s) => new Date(s.captured_at) >= cutoff)
}

interface Props {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  summaryError?: string
}

export default function AssetsTab({ summary, snapshots, summaryError }: Props) {
  const [range] = useState<Range>('1M')
  const filtered = useMemo(() => filterByRange(snapshots, range), [snapshots, range])
  if (summary) return <AssetBreakdown positions={summary.positions} snapshots={filtered} />
  if (summaryError) {
    return (
      <div
        className="text-base text-loss bg-surface-raised border border-surface-border rounded-lg p-6"
        role="status"
        aria-live="polite"
      >
        Assets unavailable: {summaryError}
      </div>
    )
  }
  return (
    <div className="text-base text-txt-muted bg-surface-raised border border-surface-border rounded-lg p-6 animate-pulse-subtle">
      Loading…
    </div>
  )
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/crypto/BalanceTab.tsx frontend/src/components/crypto/AssetsTab.tsx
git commit -m "feat(crypto): BalanceTab + AssetsTab shells reusing ChartCard and AssetBreakdown"
git push
```

---

## Task 6: Simplify `DCAHistoryTable` (5 columns + theme tokens)

**Files:** Modify: `frontend/src/components/DCAHistoryTable.tsx`

- [ ] **Step 1: Replace `DCAHistoryTable.tsx` with the slimmed version**

```tsx
import type { DCAEntry } from '../types'
import { formatAUD } from '../utils/pnl'

interface Props {
  entries: DCAEntry[]
}

export default function DCAHistoryTable({ entries }: Props) {
  return (
    <div className="bg-surface-raised border border-surface-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface/40">
            <tr className="text-txt-muted">
              <th className="text-left text-xs uppercase tracking-wider font-medium px-6 py-3">Date</th>
              <th className="text-left text-xs uppercase tracking-wider font-medium px-6 py-3">Asset</th>
              <th className="text-right text-xs uppercase tracking-wider font-medium px-6 py-3">Quantity</th>
              <th className="text-right text-xs uppercase tracking-wider font-medium px-6 py-3">Buy Price</th>
              <th className="text-right text-xs uppercase tracking-wider font-medium px-6 py-3">Cost Paid</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => {
              const date = new Date(e.acquired_at).toLocaleDateString('en-AU', {
                timeZone: 'Australia/Sydney',
                dateStyle: 'medium',
              })
              return (
                <tr
                  key={e.lot_id}
                  className="border-t border-surface-border/60 hover:bg-surface-hover/40 transition-colors"
                >
                  <td className="px-6 py-3 text-txt-secondary">{date}</td>
                  <td className="px-6 py-3 font-medium text-txt-primary">{e.asset}</td>
                  <td className="px-6 py-3 text-right text-txt-secondary tabular-nums">
                    {e.quantity.toFixed(4)}
                  </td>
                  <td className="px-6 py-3 text-right text-txt-secondary tabular-nums">
                    {formatAUD(e.cost_per_unit_aud)}
                  </td>
                  <td className="px-6 py-3 text-right text-txt-primary font-medium tabular-nums">
                    {formatAUD(e.cost_aud)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DCAHistoryTable.tsx
git commit -m "refactor(dca-table): 5 columns + theme tokens, drop inline heading"
git push
```

---

## Task 7: Build `PurchasesTab` with Sync-now button

**Files:**
- Create: `frontend/src/components/crypto/PurchasesTab.tsx`
- Create: `frontend/src/components/crypto/PurchasesTab.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/crypto/PurchasesTab.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import PurchasesTab from './PurchasesTab'

const apiFetch = vi.fn()

vi.mock('../../api/client', () => ({
  apiFetch: (...args: any[]) => apiFetch(...args),
  UNAUTHORIZED_EVENT: 'auth:unauthorized',
  SERVER_ERROR_EVENT: 'server:error',
}))

beforeEach(() => {
  apiFetch.mockReset()
})

describe('PurchasesTab Sync-now button', () => {
  it('renders empty placeholder when there are no entries', () => {
    render(<PurchasesTab entries={[]} onSynced={() => {}} dcaError={undefined} />)
    expect(screen.getByText(/no purchases recorded yet/i)).toBeInTheDocument()
  })

  it('POSTs /api/sync and shows success status', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ synced: 3, last_trade_id: 'T123' }),
    })
    const onSynced = vi.fn(() => Promise.resolve())
    render(<PurchasesTab entries={[]} onSynced={onSynced} dcaError={undefined} />)
    fireEvent.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() => expect(onSynced).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenCalledWith('/api/sync', { method: 'POST' })
    expect(await screen.findByText(/synced 3 new purchases/i)).toBeInTheDocument()
  })

  it('shows error inline when sync fails', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
      statusText: 'Server Error',
    })
    render(<PurchasesTab entries={[]} onSynced={() => Promise.resolve()} dcaError={undefined} />)
    fireEvent.click(screen.getByRole('button', { name: /sync now/i }))
    expect(await screen.findByText(/sync failed/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
cd frontend && npx vitest run src/components/crypto/PurchasesTab.test.tsx
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement `PurchasesTab.tsx`**

```tsx
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import DCAHistoryTable from '../DCAHistoryTable'
import { apiFetch } from '../../api/client'
import type { DCAEntry } from '../../types'

type SyncStatus =
  | { kind: 'idle' }
  | { kind: 'syncing' }
  | { kind: 'success'; synced: number; at: Date }
  | { kind: 'error'; message: string }

interface Props {
  entries: DCAEntry[]
  onSynced: () => Promise<void>
  dcaError: string | undefined
}

export default function PurchasesTab({ entries, onSynced, dcaError }: Props) {
  const [status, setStatus] = useState<SyncStatus>({ kind: 'idle' })

  async function handleSync() {
    setStatus({ kind: 'syncing' })
    try {
      const res = await apiFetch('/api/sync', { method: 'POST' })
      if (!res.ok) {
        setStatus({ kind: 'error', message: `Sync failed (${res.status} ${res.statusText})` })
        return
      }
      const body = (await res.json()) as { synced?: number }
      await onSynced()
      setStatus({ kind: 'success', synced: body.synced ?? 0, at: new Date() })
    } catch (err) {
      setStatus({ kind: 'error', message: `Sync failed: ${(err as Error).message}` })
    }
  }

  const isSyncing = status.kind === 'syncing'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-txt-muted">All purchases synced from Kraken.</p>
        <div className="flex items-center gap-3">
          <SyncStatusLabel status={status} />
          <button
            type="button"
            onClick={handleSync}
            disabled={isSyncing}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-surface-raised border border-surface-border text-sm text-txt-primary hover:bg-surface-hover transition-colors duration-200 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} />
            {isSyncing ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      </div>

      {dcaError ? (
        <div
          className="text-base text-loss bg-surface-raised border border-surface-border rounded-lg p-6"
          role="status"
          aria-live="polite"
        >
          Previous purchases unavailable: {dcaError}
        </div>
      ) : entries.length === 0 ? (
        <div className="text-center py-12 bg-surface-raised border border-surface-border rounded-xl">
          <p className="text-txt-muted">No purchases recorded yet.</p>
          <p className="text-sm text-txt-muted mt-1">Click Sync now to pull from Kraken.</p>
        </div>
      ) : (
        <DCAHistoryTable entries={entries} />
      )}
    </div>
  )
}

function SyncStatusLabel({ status }: { status: SyncStatus }) {
  if (status.kind === 'success') {
    return (
      <span className="text-xs text-profit">
        Synced {status.synced} new purchases · just now
      </span>
    )
  }
  if (status.kind === 'error') {
    return <span className="text-xs text-loss">{status.message}</span>
  }
  return null
}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd frontend && npx vitest run src/components/crypto/PurchasesTab.test.tsx
```

Expected: 3 PASS.

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/crypto/PurchasesTab.tsx frontend/src/components/crypto/PurchasesTab.test.tsx
git commit -m "feat(crypto): PurchasesTab with Sync-now button and inline status"
git push
```

---

## Task 8: Add `variant` prop to `AgentInput`

**Files:** Modify: `frontend/src/components/AgentInput.tsx`

- [ ] **Step 1: Read the current implementation**

Read `frontend/src/components/AgentInput.tsx` so the next edit preserves the existing focus / submit behaviour.

- [ ] **Step 2: Add `variant` prop and conditional styling**

In `frontend/src/components/AgentInput.tsx`:
- Add `variant?: 'topbar' | 'hero' | 'docked'` to the `Props` interface (default `'topbar'`).
- For `'hero'`: width `w-full max-w-[640px]`, height `h-14`, larger text `text-base`, kraken-purple focus ring `focus-within:ring-2 focus-within:ring-kraken/40`, sparkles icon left, no kbd hint.
- For `'docked'`: width `w-full`, height `h-12`, same focus ring, sparkles icon left.
- Keep the existing top-bar variant exactly as-is (it's still used elsewhere if any consumer is left).

Make the size / icon decisions via a single `const styles = variant === 'hero' ? ... : variant === 'docked' ? ... : ...` block at the top of the component to avoid scattering conditionals.

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AgentInput.tsx
git commit -m "feat(agent-input): add hero/docked variants for the redesigned Ask AI tab"
git push
```

---

## Task 9: Build `SuggestionPills`

**Files:** Create: `frontend/src/components/SuggestionPills.tsx`

- [ ] **Step 1: Implement**

```tsx
interface Props {
  suggestions: string[]
  onPick: (text: string) => void
}

export default function SuggestionPills({ suggestions, onPick }: Props) {
  return (
    <div className="flex flex-wrap justify-center gap-2 mt-8">
      {suggestions.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          className="px-4 py-2 rounded-full text-sm text-txt-secondary bg-surface-raised border border-surface-border hover:bg-surface-hover hover:text-txt-primary transition-colors duration-200"
        >
          {s}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SuggestionPills.tsx
git commit -m "feat(agent): SuggestionPills component for Ask AI empty state"
git push
```

---

## Task 10: Build `AgentConversation`

**Files:** Create: `frontend/src/components/AgentConversation.tsx`

- [ ] **Step 1: Implement**

```tsx
import AgentMessage from './AgentMessage'
import AgentToolStatus from './AgentToolStatus'
import AgentHITL from './AgentHITL'
import type { AgentMessage as AgentMessageType, ToolActivity, HITLState } from '../types/agent'

interface Props {
  messages: AgentMessageType[]
  activeTools: ToolActivity[]
  hitl: HITLState | null
  onRespondHITL: (approved: boolean) => void
}

export default function AgentConversation({ messages, activeTools, hitl, onRespondHITL }: Props) {
  return (
    <div className="space-y-6">
      {messages.map((m) => (
        <AgentMessage key={m.id} message={m} />
      ))}
      {activeTools.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {activeTools.map((t) => (
            <AgentToolStatus key={t.tool} activity={t} />
          ))}
        </div>
      )}
      {hitl?.pending && <AgentHITL state={hitl} onRespond={onRespondHITL} />}
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean. *(If `AgentToolStatus` or `AgentHITL` have different prop names than assumed, fix this file to match — they're project components and the existing usages in `AgentPanel.tsx` are the source of truth.)*

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AgentConversation.tsx
git commit -m "feat(agent): AgentConversation — vertical message stack with tools + HITL"
git push
```

---

## Task 11: Build `AskTab` (empty + active states)

**Files:**
- Create: `frontend/src/components/crypto/AskTab.tsx`
- Create: `frontend/src/components/crypto/AskTab.test.tsx`

- [ ] **Step 1: Write failing test**

Create `frontend/src/components/crypto/AskTab.test.tsx`:

```tsx
import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const send = vi.fn()
const newConversation = vi.fn()

vi.mock('../../hooks/useAgentChat', () => ({
  useAgentChat: () => ({
    messages: [],
    activeTools: [],
    hitl: null,
    thinking: false,
    connected: true,
    sessionId: null,
    send,
    respondHITL: vi.fn(),
    newConversation,
  }),
}))

import AskTab from './AskTab'

describe('AskTab', () => {
  it('renders hero empty state when there are no messages', () => {
    render(<AskTab />)
    expect(screen.getByRole('heading', { name: /how can i help/i })).toBeInTheDocument()
    expect(screen.getByText(/is my portfolio good\?/i)).toBeInTheDocument()
  })

  it('submits a question when a suggestion pill is clicked', () => {
    render(<AskTab />)
    fireEvent.click(screen.getByText(/is my portfolio good\?/i))
    expect(send).toHaveBeenCalledWith('Is my portfolio good?')
  })
})
```

- [ ] **Step 2: Run tests and verify they fail**

```bash
cd frontend && npx vitest run src/components/crypto/AskTab.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement `AskTab.tsx`**

```tsx
import { Sparkles } from 'lucide-react'
import AgentInput from '../AgentInput'
import AgentConversation from '../AgentConversation'
import SuggestionPills from '../SuggestionPills'
import NewConversationButton from '../NewConversationButton'
import { useAgentChat } from '../../hooks/useAgentChat'

const SUGGESTIONS = [
  'Is my portfolio good?',
  "What's my biggest holding?",
  'Show my recent purchases',
  'Am I up this month?',
]

export default function AskTab() {
  const agent = useAgentChat()
  const empty = agent.messages.length === 0

  if (empty) {
    return (
      <div className="relative overflow-hidden min-h-[560px] flex items-center justify-center">
        {/* Backdrop blurs — kraken purple + accent teal, not generic AI blue */}
        <div
          aria-hidden
          className="absolute top-0 right-0 w-[420px] h-[420px] rounded-full bg-kraken/30 blur-3xl opacity-30 pointer-events-none"
        />
        <div
          aria-hidden
          className="absolute bottom-0 left-0 w-[420px] h-[420px] rounded-full bg-accent/20 blur-3xl opacity-30 pointer-events-none"
        />
        <div className="relative w-full max-w-[640px] flex flex-col items-center text-center px-6">
          <div className="bg-kraken/10 p-3 rounded-2xl mb-6">
            <Sparkles className="w-6 h-6 text-kraken" />
          </div>
          <h1 className="text-3xl font-semibold text-txt-primary tracking-tight">
            How can I help with your portfolio?
          </h1>
          <p className="text-txt-muted mt-3 text-base">
            Ask anything about your holdings, P&amp;L, or recent purchases.
          </p>
          <div className="w-full mt-8">
            <AgentInput variant="hero" onSubmit={(text) => agent.send(text)} />
          </div>
          <SuggestionPills suggestions={SUGGESTIONS} onPick={(s) => agent.send(s)} />
        </div>
      </div>
    )
  }

  return (
    <div className="relative">
      <div className="flex justify-end mb-2">
        <NewConversationButton onClick={agent.newConversation} />
      </div>
      <div className="max-w-[720px] mx-auto pb-32">
        <AgentConversation
          messages={agent.messages}
          activeTools={agent.activeTools}
          hitl={agent.hitl}
          onRespondHITL={agent.respondHITL}
        />
      </div>
      <div className="sticky bottom-4 max-w-[720px] mx-auto">
        <AgentInput variant="docked" onSubmit={(text) => agent.send(text)} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd frontend && npx vitest run src/components/crypto/AskTab.test.tsx
```

Expected: 2 PASS.

- [ ] **Step 5: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean. If `AgentInput`'s `onSubmit` signature doesn't match the call here, fix Task 8's variant work first.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/crypto/AskTab.tsx frontend/src/components/crypto/AskTab.test.tsx
git commit -m "feat(crypto): AskTab with hero empty state + chat active state"
git push
```

---

## Task 12: Refactor `CryptoPage` into the tab router

**Files:** Modify: `frontend/src/pages/CryptoPage.tsx`

- [ ] **Step 1: Replace the file contents**

```tsx
import { useEffect, useState } from 'react'
import { useCryptoData } from '../hooks/useCryptoData'
import { useAgentChat } from '../hooks/useAgentChat'
import CryptoTabBar, { useActiveTab } from '../components/crypto/CryptoTabBar'
import BalanceTab from '../components/crypto/BalanceTab'
import AssetsTab from '../components/crypto/AssetsTab'
import PurchasesTab from '../components/crypto/PurchasesTab'
import AskTab from '../components/crypto/AskTab'
import SignOutButton from '../components/SignOutButton'
import ErrorBanner from '../components/ErrorBanner'
import { SERVER_ERROR_EVENT, type ServerErrorDetail } from '../api/client'

interface Props {
  onSignedOut: () => void
}

export default function CryptoPage({ onSignedOut }: Props) {
  const data = useCryptoData()
  const { active } = useActiveTab()
  const [serverError, setServerError] = useState<ServerErrorDetail | null>(null)

  useEffect(() => {
    function handle(e: Event) {
      setServerError((e as CustomEvent<ServerErrorDetail>).detail)
    }
    window.addEventListener(SERVER_ERROR_EVENT, handle)
    return () => window.removeEventListener(SERVER_ERROR_EVENT, handle)
  }, [])

  return (
    <div className="min-h-screen bg-surface text-txt-primary font-sans">
      <div className="px-8 pt-6">
        <div className="w-full max-w-[1600px] mx-auto flex items-center justify-end">
          <SignOutButton onSignedOut={onSignedOut} />
        </div>
      </div>

      {serverError && (
        <ErrorBanner
          detail={serverError}
          onRetry={() => {
            setServerError(null)
            data.refresh()
          }}
          onDismiss={() => setServerError(null)}
        />
      )}

      <div className="w-full max-w-[1600px] mx-auto px-8 pt-6">
        <CryptoTabBar />
      </div>

      <div className="w-full max-w-[1600px] mx-auto px-8 py-8">
        {active === 'balance' && (
          <BalanceTab
            summary={data.summary}
            snapshots={data.snapshots}
            refreshing={data.refreshing}
            onRefresh={data.refresh}
            summaryError={data.errors.summary}
            snapshotsError={data.errors.snapshots}
          />
        )}
        {active === 'assets' && (
          <AssetsTab
            summary={data.summary}
            snapshots={data.snapshots}
            summaryError={data.errors.summary}
          />
        )}
        {active === 'purchases' && (
          <PurchasesTab
            entries={data.dcaHistory}
            onSynced={data.refresh}
            dcaError={data.errors.dca}
          />
        )}
        {active === 'ask' && <AskTab />}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Manual smoke test in the browser**

Visit `http://localhost:5173/crypto`. Switch through all four tabs. Reload after each switch. Confirm `?tab=` updates in the URL, the active underline tracks correctly, and content swaps cleanly.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CryptoPage.tsx
git commit -m "refactor(crypto): collapse CryptoPage to tab router + sign-out"
git push
```

---

## Task 13: `/critique` pass — find any remaining AI-slop signals

**Files:** No code changes in this task; fixes happen in Task 14.

- [ ] **Step 1: Invoke the `critique` skill**

Open the `/crypto` page in the browser. Walk through each tab. Then invoke the `critique` skill against the redesigned surface (screenshots welcome). Capture the findings.

- [ ] **Step 2: Record findings here**

Edit this file and write a short bulleted list under the **"Critique findings"** heading below — `P0` items first, then `P1`, then `P2`.

### Critique findings

*(Filled in during Step 2 — leave this header here; do not delete it.)*

- [ ] **Step 3: Commit the findings**

```bash
git add docs/superpowers/plans/2026-05-26-crypto-page-redesign.md
git commit -m "docs(plan): record /critique findings against redesigned /crypto"
git push
```

---

## Task 14: Address `P0` and `P1` critique findings + final `/polish` pass

**Files:** Whatever files the findings dictate. Touch only what the critique surfaced.

- [ ] **Step 1: Fix each `P0` finding**

For each `P0` listed under "Critique findings", implement the minimal fix. Type-check after each. Commit each fix on its own line so it's reviewable independently.

```bash
cd frontend && npx tsc --noEmit
git add <files>
git commit -m "fix(crypto): <one-line description of critique finding>"
```

- [ ] **Step 2: Fix each `P1` finding** (same pattern as Step 1)

- [ ] **Step 3: Run the `polish` skill on the page**

Invoke `polish`. Apply its alignment / spacing / micro-detail suggestions.

- [ ] **Step 4: Run all frontend tests**

```bash
cd frontend && npm run test
```

Expected: all tests PASS.

- [ ] **Step 5: Final type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Final smoke test**

In the browser at `http://localhost:5173/crypto`:

1. All four tabs load.
2. `?tab=` round-trips through refresh.
3. On Previous Purchases: click "Sync now". Confirm button disables, status updates, table re-renders if there's new data.
4. On Ask AI empty state: click a suggestion pill. Confirm the surface flips to the active conversation state.
5. Ask "show me a snapshot of my portfolio" — confirm the agent's markdown table renders as a styled HTML table, bold renders, headings render, code fences render.
6. Reload the page mid-conversation — confirm messages rehydrate without crashing (verifies the earlier flatten fixes still hold).
7. Open DevTools Console — confirm zero errors / warnings related to the redesign.

- [ ] **Step 7: Final commit + push**

```bash
git add -A
git commit -m "polish(crypto): final pass — alignment, spacing, micro-details"
git push
```

---

## Self-review pass

Walk this section after writing the plan. Fix any gap inline.

### Spec coverage map

| Spec requirement | Task that implements it |
|---|---|
| Four tabs (Balance / Asset Breakdown / Previous Purchases / Ask AI) | T4, T5, T6, T7, T11 |
| URL search-param `?tab=` state with default + unknown-value fallback | T4 |
| Top bar drops the inline `AgentInput` and right-rail `AgentPanel`; keeps Sign out | T12 |
| `useCryptoData` data layer extracted | T3 |
| Previous Purchases: 5 columns, theme tokens, no inline heading | T6 |
| Previous Purchases: Sync-now button + success/error inline status | T7 |
| Ask AI hero empty state: sparkles + headline + subtitle + pill input + 4 suggestion pills | T9, T11 |
| Ask AI active state: vertical conversation + docked input + New conversation button | T10, T11 |
| Backdrop blurs use kraken/accent tokens, not generic blue | T11 |
| Markdown: `remark-gfm` + full component-map styling | T1, T2 |
| Tables, headings, bold, lists, inline code, fenced code, blockquotes all render styled | T2 |
| String-coercion guard for non-string content stays in place | T2 |
| Anti-slop chain (`redesign-existing-projects` → `/impeccable craft` → `design-taste-frontend` discipline → `/critique` → `/polish`) | T0, T13, T14 |

### Placeholder scan

Scanned: no "TBD", no "TODO", no "implement later", no "add appropriate error handling" without code, no "similar to Task N" without repeating, no references to types/components not defined in the plan or pre-existing in the project.

### Type / name consistency

- `useActiveTab` is exported alongside `CryptoTabBar` and consumed by `CryptoPage` (T4 + T12). Signature: `() => { active: string; setActive: (id: string) => void }`. Consistent.
- `useCryptoData` returns `{ summary, snapshots, dcaHistory, errors, refreshing, refresh }`. Consumed in T12 with those exact names. Consistent.
- `PurchasesTab` props `entries / onSynced / dcaError`. T7 + T12 consistent.
- `AgentInput` `variant` is `'topbar' | 'hero' | 'docked'`. T8 + T11 consistent. T11 uses `'hero'` and `'docked'`.
- `SuggestionPills` props `suggestions / onPick`. T9 + T11 consistent.
- `AgentConversation` props `messages / activeTools / hitl / onRespondHITL`. T10 + T11 consistent.

---

## Execution handoff

Plan complete. Choose execution mode after reading.
