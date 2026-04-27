# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the authenticated dashboard's chart card and asset breakdown to match the polish of the rest of the app, fix the backend backfill bug that produces misleading dips in the portfolio chart, and remove the layout cap that leaves the right half of wide screens empty.

**Architecture:** Hybrid aesthetic — kraken-violet brand chrome stays; chart and breakdown adopt a teal accent. `SummaryBar` and `PortfolioLineChart` are replaced by a single `ChartCard` (balance hero + range pills + chart + total/per-asset toggle). `AssetBreakdown` is rewritten as a stacked allocation bar plus per-asset rows with sparklines. One backend line — adding `XETH.B` to `ASSET_MAP["ETH"]["keys"]` — fixes the snapshot data quality issue; the snapshots table is wiped and rebuilt as a one-off post-deploy step.

**Tech Stack:** React + TypeScript + Vite, Tailwind CSS, Recharts (already in use), FastAPI + Supabase Postgres on the backend.

**Spec:** `docs/superpowers/specs/2026-04-27-dashboard-redesign-design.md`

**Implementation context:**
- All frontend + backend changes happen in the existing **`tax-hub-foundation`** worktree at `.claude/worktrees/tax-hub-foundation/`. That branch already has the SideRail and TaxHub the dashboard sits inside; cutting a new worktree from `main` would lose that scaffolding.
- Backend tests run via `backend/.venv/bin/pytest` from the worktree root.
- Backend dev server: assume the user has it running locally on `http://localhost:8000`. Restarting after the Task 1 commit is required for the asset-map change to take effect.
- Frontend: no test framework is set up; pure-logic helpers can be tested manually via `node`/`tsx` one-liners or by building. Do not introduce Vitest in this plan — that's scope creep.
- Per project preference, **invoke the `impeccable` skill before writing JSX for any visual component** (Tasks 4, 5, 7, 8). Don't hand-roll Tailwind for those tasks.
- After every task: `git push` is the final step. The user reviews each commit on GitHub.

---

## File Structure

**New files (frontend):**
- `frontend/src/utils/assetColors.ts` — single source of truth for per-asset stroke/fill colours.
- `frontend/src/utils/portfolioRange.ts` — pure helpers: `unionAssetKeys(snapshots)` and `computeRangeDelta(snapshots)`.
- `frontend/src/components/Sparkline.tsx` — tiny inline line chart, used inside breakdown rows.
- `frontend/src/components/AllocationStackBar.tsx` — full-width stacked allocation bar at the top of the breakdown card.
- `frontend/src/components/ChartCard.tsx` — replaces `SummaryBar` + `PortfolioLineChart` as a single component with balance hero, range pills, total/per-asset toggle, and the styled chart.

**Modified files:**
- `frontend/tailwind.config.js` — add `accent` colour token (teal) and `asset.link` colour.
- `frontend/src/pages/Dashboard.tsx` — render `<ChartCard />` + `<AssetBreakdown />` + `<DCAHistoryTable />`; remove `max-w-7xl mx-auto` cap.
- `frontend/src/components/AssetBreakdown.tsx` — full rewrite (no `<table>`); uses `AllocationStackBar` and `Sparkline`.
- `backend/config/assets.py` — add `"XETH.B"` to `ASSET_MAP["ETH"]["keys"]`.
- `backend/tests/test_assets_config.py` — regression test for the new mapping.

**Deleted files:**
- `frontend/src/components/SummaryBar.tsx`
- `frontend/src/components/PortfolioLineChart.tsx`

---

## Task 1: Backend — fix the XETH.B mapping and rebuild snapshots

**Files:**
- Modify: `.claude/worktrees/tax-hub-foundation/backend/config/assets.py`
- Modify: `.claude/worktrees/tax-hub-foundation/backend/tests/test_assets_config.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_assets_config.py`:

```python
def test_xeth_bonded_maps_to_eth():
    """Regression: bonded ETH ledger code must map to ETH so backfill walks the
    transfer pair correctly. Without this, every backfilled snapshot ends up
    with ETH=0 because the inbound transfer is unmapped while the offsetting
    XETH debit is applied. See spec 2026-04-27-dashboard-redesign-design §6.
    """
    assert BALANCE_KEY_TO_DISPLAY["XETH.B"] == "ETH"
    assert "XETH.B" in ASSET_MAP["ETH"]["keys"]
```

- [ ] **Step 2: Run test to verify it fails**

Run from the worktree root:
```bash
backend/.venv/bin/pytest backend/tests/test_assets_config.py::test_xeth_bonded_maps_to_eth -v
```
Expected: `FAILED` — `KeyError: 'XETH.B'` in the first assertion.

- [ ] **Step 3: Add `XETH.B` to the asset map**

In `backend/config/assets.py`, change the ETH entry:

```python
"ETH": {
    "keys": ["XETH", "ETH", "ETH.B", "XETH.B", "ETH.S", "ETH2", "ETH2.S", "ETH.F"],
    "pair": "ETHAUD",
},
```

(`"XETH.B"` inserted after `"ETH.B"`. No other changes.)

- [ ] **Step 4: Run the regression test to verify it passes**

```bash
backend/.venv/bin/pytest backend/tests/test_assets_config.py -v
```
Expected: every test in the file passes, including the new one.

- [ ] **Step 5: Run the full backend test suite to confirm no regressions**

```bash
backend/.venv/bin/pytest backend/tests -v
```
Expected: previously-green tests stay green. (One pre-existing failure in `test_mcp_server.py::test_get_prices_tool_default_assets` may persist — that's unrelated to this work and is documented in Phase 4 memory.)

- [ ] **Step 6: Restart the backend so the running process picks up the new mapping**

The user has the backend running locally. Stop and restart it (the user can do this; if you have access to the process, restart yourself). The asset map is loaded at import time, so a hot reload that does not re-import `backend.config.assets` will not pick up the change.

- [ ] **Step 7: Wipe and rebuild the snapshots table**

This is a destructive one-off operation, but the existing snapshots are mostly wrong (every backfilled row has `ETH=0`). The endpoint already exists.

```bash
curl -X POST 'http://localhost:8000/api/history/backfill?clear=true' \
     -H "Cookie: auth_token=$AUTH_COOKIE"
```

`AUTH_COOKIE` is the session cookie from the user's browser (DevTools → Application → Cookies → `auth_token`). Expected response shape: `{"cleared": <N>, "created": <M>}` with `M > 0`.

- [ ] **Step 8: Verify the spike is gone**

```bash
backend/.venv/bin/python -c "
from backend.repositories import snapshots_repo
rows = snapshots_repo.get_all(from_dt='2026-04-15', to_dt='2026-04-30')
for r in rows:
    eth = r.assets.get('ETH')
    eth_str = f'ETH={eth.value_aud:.0f}' if eth else 'no ETH'
    print(f'{r.captured_at}  total={r.total_value_aud:>8.0f}  {eth_str}')
"
```
Expected: every row in the suspect window shows `ETH ≈ 3700–3900` (not `ETH=0`), and `total ≈ 5800–6200`. No row should have `ETH=0` for a date the user actually held bonded ETH.

- [ ] **Step 9: Commit and push**

```bash
git add backend/config/assets.py backend/tests/test_assets_config.py
git commit -m "$(cat <<'EOF'
fix(assets): map XETH.B ledger code to ETH so backfill captures bonded balance

The bonded ETH ledger pair (receive on XETH, transfer to XETH.B, offsetting
debit on XETH) was netting to zero in the running balance because XETH.B was
unmapped. Every backfilled snapshot ended up with ETH=0 while live snapshots
showed the real ~$3.8k ETH value, producing a misleading "drop and spike"
in the portfolio chart. Adding XETH.B to ASSET_MAP["ETH"]["keys"] fixes it;
re-running backfill regenerates a smooth historical curve.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 2: Frontend — extend Tailwind tokens for the chart accent

**Files:**
- Modify: `.claude/worktrees/tax-hub-foundation/frontend/tailwind.config.js`

- [ ] **Step 1: Add the `accent` and `asset.link` colours**

In `frontend/tailwind.config.js`, replace the `extend.colors` block with:

```js
extend: {
  colors: {
    // Brand accent — used as punctuation, not decoration
    kraken: {
      DEFAULT: '#7B61FF',
      light: '#9B85FF',
      dark: '#6248E5',
      subtle: '#7B61FF1A', // 10% opacity for tinted backgrounds
    },
    // Chart accent — teal/cyan used by ChartCard and AssetBreakdown
    accent: {
      DEFAULT: '#5EEAD4',
      glow: 'rgba(94, 234, 212, 0.35)',
      subtle: 'rgba(94, 234, 212, 0.12)',
    },
    // Semantic P&L — always paired with +/- prefix
    profit: '#22C55E',
    loss: '#EF4444',
    // Asset identity colors
    asset: {
      eth: '#5EEAD4',  // teal — flagship, matches chart total accent
      sol: '#7B61FF',  // kraken violet — second voice
      ada: '#60A5FA',  // blue
      link: '#22D3EE', // teal-2 (cyan)
    },
    // Purple-tinted neutral surfaces (brand cohesion)
    surface: {
      DEFAULT: '#0f0e14',   // main page bg
      raised: '#1a1823',    // cards, elevated panels
      border: '#2a2735',    // borders, dividers
      hover: '#252230',     // hover state on raised
    },
    // Text colors (slightly warm to complement purple surfaces)
    txt: {
      primary: '#f0eef5',
      secondary: '#9691a8',
      muted: '#5f5a70',
    },
  },
},
```

(Changes: added `accent` block; rewrote `asset` block — ETH→teal, SOL→violet, ADA→blue, LINK→teal-2 per spec §4.3.)

- [ ] **Step 2: Verify the build still compiles**

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npm run build
```
Expected: build succeeds. (Existing components that referenced `bg-asset-eth`, `text-asset-sol` etc. will now render in the new palette — that is intentional.)

- [ ] **Step 3: Commit and push**

```bash
git add frontend/tailwind.config.js
git commit -m "$(cat <<'EOF'
feat(frontend): add accent (teal) and asset.link colour tokens

Adds the chart accent palette used by ChartCard and AssetBreakdown
(teal #5EEAD4 with glow + subtle variants) and remaps the asset palette
to the new ETH=teal / SOL=violet / ADA=blue / LINK=teal-2 scheme defined
in the dashboard redesign spec.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 3: Frontend — `assetColors.ts` utility

**Files:**
- Create: `.claude/worktrees/tax-hub-foundation/frontend/src/utils/assetColors.ts`

- [ ] **Step 1: Create the utility file**

`frontend/src/utils/assetColors.ts`:

```ts
/**
 * Single source of truth for per-asset chart/sparkline/segment colours.
 *
 * Returns the hex value (not a Tailwind class) because Recharts' stroke/fill
 * props need raw colours. For Tailwind contexts (bg-asset-eth etc.), use the
 * tokens directly — the values here mirror the tailwind.config.js asset block.
 */

const ASSET_COLORS: Record<string, string> = {
  ETH: '#5EEAD4',  // accent teal — flagship
  SOL: '#7B61FF',  // kraken violet
  ADA: '#60A5FA',  // blue
  LINK: '#22D3EE', // teal-2 (cyan)
}

const FALLBACK = '#5f5a70' // txt-muted — neutral grey for unknown assets

export function colorForAsset(asset: string): string {
  return ASSET_COLORS[asset] ?? FALLBACK
}

export function knownAssets(): string[] {
  return Object.keys(ASSET_COLORS)
}
```

- [ ] **Step 2: Commit and push**

```bash
git add frontend/src/utils/assetColors.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add assetColors utility — single source of truth for chart hues

Centralises the per-asset hex values used by ChartCard, Sparkline, and
AllocationStackBar. Mirrors the tailwind tokens in asset.{eth,sol,ada,link}
so Tailwind classes and Recharts stroke/fill stay in lockstep.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 4: Frontend — `Sparkline` component

**Files:**
- Create: `.claude/worktrees/tax-hub-foundation/frontend/src/components/Sparkline.tsx`

- [ ] **Step 1: Invoke `/impeccable` for the visual implementation**

Per the project's frontend convention, the visual implementation of Sparkline goes through the `impeccable` skill. Invoke it before writing the JSX. Brief the skill with: "Tiny inline line chart, ~120×28px, single coloured stroke, no axes, no labels, no fill, no tooltip — purely decorative trendline rendered inside an asset breakdown row. Must handle 0/1/N data points gracefully."

- [ ] **Step 2: Implement `Sparkline.tsx` per the spec and impeccable's guidance**

`frontend/src/components/Sparkline.tsx`:

```tsx
import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface Props {
  /** Series of values to plot. Order = chronological. */
  values: number[]
  /** Hex stroke colour. */
  color: string
  /** Container height in px. Default 28. */
  height?: number
}

/**
 * Decorative inline sparkline. No axes, no tooltip, no labels.
 * Renders a flat line for length-1 series; an empty box for length-0.
 */
export default function Sparkline({ values, color, height = 28 }: Props) {
  if (values.length === 0) {
    return <div style={{ height }} className="w-full" aria-hidden="true" />
  }

  // Recharts needs at least 2 points to render a line — duplicate a single
  // point so the user sees a flat trendline rather than nothing.
  const data = (values.length === 1 ? [values[0], values[0]] : values).map((v, i) => ({
    i,
    v,
  }))

  return (
    <div style={{ height }} className="w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 3: Sanity-check the build**

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/components/Sparkline.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add Sparkline component (/impeccable)

Tiny inline line chart for use inside AssetBreakdown rows. Purely decorative
(no axes, tooltip, or labels), gracefully handles 0/1/N data points.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 5: Frontend — `AllocationStackBar` component

**Files:**
- Create: `.claude/worktrees/tax-hub-foundation/frontend/src/components/AllocationStackBar.tsx`

- [ ] **Step 1: Invoke `/impeccable` for the visual implementation**

Brief: "Full-width horizontal stacked bar inside an asset-breakdown card. Shows allocation by asset — one segment per asset, width proportional to allocation %. Each segment uses its asset's hex hue from `colorForAsset`. 1px gap between segments. Hover lifts brightness and reveals a tooltip card with `<asset> · <allocation_pct>% · <value_aud>`. Height ~10px (h-2.5). Rounded-full container, segments don't independently round."

- [ ] **Step 2: Implement `AllocationStackBar.tsx`**

`frontend/src/components/AllocationStackBar.tsx`:

```tsx
import { useState } from 'react'
import type { AssetPosition } from '../types'
import { colorForAsset } from '../utils/assetColors'
import { formatAUD, formatPct } from '../utils/pnl'

interface Props {
  positions: AssetPosition[]
}

export default function AllocationStackBar({ positions }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)

  // Sort by allocation desc so the largest asset anchors the left edge.
  const sorted = [...positions]
    .filter((p) => p.allocation_pct > 0)
    .sort((a, b) => b.allocation_pct - a.allocation_pct)

  if (sorted.length === 0) {
    return <div className="h-2.5 w-full rounded-full bg-surface-border/40" />
  }

  const tooltipFor = sorted.find((p) => p.asset === hovered)

  return (
    <div className="relative">
      <div className="h-2.5 w-full rounded-full overflow-hidden flex gap-px bg-surface-border/40">
        {sorted.map((p) => (
          <button
            key={p.asset}
            type="button"
            onMouseEnter={() => setHovered(p.asset)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(p.asset)}
            onBlur={() => setHovered(null)}
            aria-label={`${p.asset} ${formatPct(p.allocation_pct)} ${formatAUD(p.value_aud)}`}
            className="h-full transition-[filter,transform] duration-150 ease-out hover:brightness-125 focus:brightness-125 focus:outline-none"
            style={{
              flexGrow: p.allocation_pct,
              flexBasis: 0,
              backgroundColor: colorForAsset(p.asset),
            }}
          />
        ))}
      </div>

      {tooltipFor && (
        <div
          role="tooltip"
          className="absolute left-1/2 -translate-x-1/2 -top-12 z-10 pointer-events-none whitespace-nowrap rounded-md border border-surface-border bg-surface-raised/95 backdrop-blur-sm px-3 py-1.5 text-xs text-txt-primary shadow-lg"
        >
          <span className="font-mono font-medium" style={{ color: colorForAsset(tooltipFor.asset) }}>
            {tooltipFor.asset}
          </span>
          <span className="text-txt-muted"> · </span>
          <span className="font-mono">{formatPct(tooltipFor.allocation_pct)}</span>
          <span className="text-txt-muted"> · </span>
          <span className="font-mono">{formatAUD(tooltipFor.value_aud)}</span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Sanity-check the build**

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npm run build
```
Expected: build succeeds.

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/components/AllocationStackBar.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add AllocationStackBar component (/impeccable)

Full-width horizontal stacked allocation bar with per-asset segments,
hover lift + tooltip. Renders at the top of the asset breakdown card
to surface portfolio shape at a glance.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 6: Frontend — pure helpers `portfolioRange.ts`

**Files:**
- Create: `.claude/worktrees/tax-hub-foundation/frontend/src/utils/portfolioRange.ts`

- [ ] **Step 1: Create the utility file**

`frontend/src/utils/portfolioRange.ts`:

```ts
import type { PortfolioSnapshot } from '../types'

/**
 * Union of asset keys across every snapshot in the array. Used by the chart
 * card's per-asset legend so assets added late in the history (e.g. LINK)
 * still appear, even though the earliest snapshots predate them.
 */
export function unionAssetKeys(snapshots: PortfolioSnapshot[]): string[] {
  const set = new Set<string>()
  for (const s of snapshots) {
    for (const k of Object.keys(s.assets)) {
      set.add(k)
    }
  }
  return Array.from(set)
}

/**
 * Range-relative percentage delta between the first and last snapshot of
 * the filtered window. Returns null if fewer than two snapshots exist or
 * if the start value is zero (would divide by zero).
 */
export function computeRangeDelta(snapshots: PortfolioSnapshot[]): number | null {
  if (snapshots.length < 2) return null
  const start = snapshots[0].total_value_aud
  const end = snapshots[snapshots.length - 1].total_value_aud
  if (start === 0) return null
  return ((end - start) / start) * 100
}
```

- [ ] **Step 2: Smoke-test by typechecking**

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npx tsc --noEmit
```
Expected: no type errors.

- [ ] **Step 3: Commit and push**

```bash
git add frontend/src/utils/portfolioRange.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add portfolioRange utils (unionAssetKeys, computeRangeDelta)

Pure helpers for the redesigned ChartCard. unionAssetKeys fixes the
per-asset legend regression where LINK was dropped because it didn't
appear in the earliest snapshot of the range. computeRangeDelta drives
the new balance-hero delta chip.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 7: Frontend — `ChartCard` component (replaces `SummaryBar` + `PortfolioLineChart`)

**Files:**
- Create: `.claude/worktrees/tax-hub-foundation/frontend/src/components/ChartCard.tsx`

- [ ] **Step 1: Review the spec sections this implements**

Open `docs/superpowers/specs/2026-04-27-dashboard-redesign-design.md` and re-read §4.1 (header — balance hero), §4.2 (controls row — range pills + total/per-asset toggle), and §4.3 (the chart — gradient fill, glow, hover crosshair, custom tooltip, per-asset palette). The ChartCard is the largest single component in the redesign; treat the spec as the contract.

- [ ] **Step 2: Invoke `/impeccable` for the visual implementation**

Brief: "Trading-terminal-style portfolio chart card. Three vertical zones inside one rounded card with `bg-surface-raised border border-surface-border p-6`:
1. Balance hero row — small kraken-violet circular icon + 'Balance' label + big mono `$X,XXX.XX AUD` number, inline range-relative delta chip (green/red), right-side last-updated timestamp + refresh icon button.
2. Controls row — `1W` `1M` `3M` `1Y` `ALL` pills (active state in teal accent), vertical hairline divider, `Total / Per Asset` segmented control.
3. Chart area — Recharts `<ComposedChart>` with: teal stroked line (`#5EEAD4`, width 1.75), gradient `<defs>` fill from teal/22% at top to transparent at bottom, faint outer glow on the line via translucent second `<Line>`, subtle horizontal grid lines, custom tooltip card on hover, dashed vertical crosshair line. In per-asset mode the gradient fill is dropped and one line per asset is drawn using `colorForAsset(asset)`. Legend dots in the controls row replace the Recharts `<Legend>`. Empty state: `'No snapshot history yet — data appears after the first hourly capture.'` Loading state: pulsed placeholder on the balance number, muted 'Loading...' centred in the chart area."

- [ ] **Step 3: Implement `ChartCard.tsx`**

`frontend/src/components/ChartCard.tsx`:

```tsx
import { useMemo } from 'react'
import {
  Area, ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { RefreshCw } from 'lucide-react'
import type { PortfolioSummary, PortfolioSnapshot } from '../types'
import { formatAUD } from '../utils/pnl'
import { colorForAsset } from '../utils/assetColors'
import { unionAssetKeys, computeRangeDelta } from '../utils/portfolioRange'

export type Range = '1W' | '1M' | '3M' | '1Y' | 'ALL'
type View = 'total' | 'per-asset'

const RANGE_OPTIONS: Range[] = ['1W', '1M', '3M', '1Y', 'ALL']

interface Props {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  range: Range
  onRangeChange: (range: Range) => void
  view: View
  onViewChange: (view: View) => void
  onRefresh: () => void
  refreshing: boolean
  summaryError?: string
  snapshotsError?: string
}

function formatRelativeTime(isoString: string): string {
  const d = new Date(isoString)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const time = d.toLocaleTimeString('en-AU', {
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
  if (isToday) return time
  return `${d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short' })}, ${time}`
}

function formatAxisDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('en-AU', {
    day: '2-digit', month: 'short', timeZone: 'Australia/Sydney',
  })
}

interface TooltipPayloadEntry {
  value: number
  name: string
  color: string
  dataKey: string
}

function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: TooltipPayloadEntry[]
  label?: string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-md border border-surface-border bg-surface-raised/95 backdrop-blur-sm px-3 py-2 shadow-lg pointer-events-none">
      <div className="flex flex-col gap-1">
        {payload
          .filter((p) => p.dataKey !== 'totalGlow')
          .map((p) => (
            <div key={p.dataKey} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: p.color }}
              />
              <span className="text-xs text-txt-muted font-medium">{p.name}</span>
              <span className="ml-auto font-mono text-sm text-txt-primary">
                {formatAUD(p.value)}
              </span>
            </div>
          ))}
      </div>
      {label && (
        <div className="mt-1 pt-1 border-t border-surface-border/50 text-[10px] text-txt-muted">
          {label}
        </div>
      )}
    </div>
  )
}

export default function ChartCard({
  summary, snapshots, range, onRangeChange, view, onViewChange,
  onRefresh, refreshing, summaryError, snapshotsError,
}: Props) {
  const data = useMemo(() => snapshots.map((s) => {
    const row: Record<string, number | string> = {
      date: s.captured_at,
      dateLabel: formatAxisDate(s.captured_at),
      total: s.total_value_aud,
    }
    for (const [asset, info] of Object.entries(s.assets)) {
      row[asset] = info.value_aud
    }
    return row
  }), [snapshots])

  const assets = useMemo(() => unionAssetKeys(snapshots), [snapshots])
  const rangeDelta = useMemo(() => computeRangeDelta(snapshots), [snapshots])

  const balance = summary?.total_value_aud ?? null
  const lastUpdated = summary?.captured_at

  const deltaSign = rangeDelta === null ? null : rangeDelta >= 0 ? 'pos' : 'neg'
  const deltaTone =
    deltaSign === 'pos'
      ? 'bg-profit/10 text-profit border-profit/20'
      : deltaSign === 'neg'
        ? 'bg-loss/10 text-loss border-loss/20'
        : ''

  return (
    <section
      aria-label="Portfolio value"
      className="bg-surface-raised border border-surface-border rounded-lg p-6"
    >
      {/* Zone 1 — balance hero row */}
      <div className="flex items-start justify-between gap-6 mb-5">
        <div className="flex items-start gap-3 min-w-0">
          <span
            aria-hidden="true"
            className="mt-1 inline-flex h-7 w-7 items-center justify-center rounded-md bg-kraken/15"
          >
            <span className="h-2 w-2 rounded-full bg-kraken" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium text-txt-muted leading-none mb-2">
              Balance
            </p>
            <div className="flex items-baseline gap-2 flex-wrap">
              {balance !== null ? (
                <span className="text-display font-bold font-mono text-txt-primary">
                  {formatAUD(balance)}
                </span>
              ) : (
                <span className={`text-display font-bold font-mono text-txt-muted ${!summaryError ? 'animate-pulse' : ''}`}>
                  {summaryError ?? '—'}
                </span>
              )}
              <span className="text-base text-txt-muted font-medium">AUD</span>
              {rangeDelta !== null && (
                <span
                  className={`ml-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-mono font-medium ${deltaTone}`}
                  aria-label={`${rangeDelta >= 0 ? 'up' : 'down'} ${Math.abs(rangeDelta).toFixed(1)} percent over ${range}`}
                >
                  {rangeDelta >= 0 ? '+' : ''}
                  {rangeDelta.toFixed(1)}% · {range}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {lastUpdated && (
            <span className="text-xs text-txt-muted whitespace-nowrap hidden sm:inline">
              Last updated {formatRelativeTime(lastUpdated)}
            </span>
          )}
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="Refresh portfolio"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-surface-border text-txt-secondary hover:text-txt-primary hover:border-kraken/40 active:scale-95 disabled:opacity-50 transition-[colors,transform]"
          >
            <RefreshCw
              className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`}
              strokeWidth={1.75}
            />
          </button>
        </div>
      </div>

      {/* Zone 2 — controls row */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <div role="tablist" aria-label="Time range" className="flex items-center gap-1 rounded-md bg-surface/40 p-1">
          {RANGE_OPTIONS.map((r) => {
            const active = r === range
            return (
              <button
                key={r}
                role="tab"
                aria-selected={active}
                type="button"
                onClick={() => onRangeChange(r)}
                className={[
                  'rounded px-2.5 py-1 text-xs font-medium font-mono tracking-tight',
                  'transition-[background-color,color] duration-150',
                  active
                    ? 'bg-accent/15 text-accent'
                    : 'text-txt-muted hover:text-txt-primary',
                ].join(' ')}
              >
                {r}
              </button>
            )
          })}
        </div>

        <span className="h-4 w-px bg-surface-border" aria-hidden="true" />

        <div role="tablist" aria-label="View mode" className="flex items-center gap-1 rounded-md bg-surface/40 p-1">
          {(['total', 'per-asset'] as View[]).map((v) => {
            const active = v === view
            return (
              <button
                key={v}
                role="tab"
                aria-selected={active}
                type="button"
                onClick={() => onViewChange(v)}
                className={[
                  'rounded px-2.5 py-1 text-xs font-medium tracking-tight',
                  'transition-[background-color,color] duration-150',
                  active
                    ? 'bg-accent/15 text-accent'
                    : 'text-txt-muted hover:text-txt-primary',
                ].join(' ')}
              >
                {v === 'total' ? 'Total' : 'Per asset'}
              </button>
            )
          })}
        </div>

        {view === 'per-asset' && (
          <div className="flex items-center gap-3 ml-2">
            {assets.map((asset) => (
              <span key={asset} className="inline-flex items-center gap-1.5 text-xs text-txt-secondary font-mono">
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: colorForAsset(asset) }}
                />
                {asset}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Zone 3 — chart */}
      <div className="h-[320px]">
        {snapshots.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-sm text-txt-muted">
              {snapshotsError
                ? `Chart unavailable: ${snapshotsError}`
                : 'No snapshot history yet — data appears after the first hourly capture.'}
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
              <defs>
                <linearGradient id="totalFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5EEAD4" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#5EEAD4" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgb(240 238 245 / 0.06)" vertical={false} />
              <XAxis
                dataKey="dateLabel"
                stroke="#5f5a70"
                tick={{ fontSize: 11, fill: '#9691a8' }}
                tickLine={false}
                axisLine={{ stroke: 'rgb(240 238 245 / 0.06)' }}
                minTickGap={48}
              />
              <YAxis
                stroke="#5f5a70"
                tick={{ fontSize: 11, fill: '#9691a8' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(0)}k`}
                width={48}
              />
              <Tooltip
                content={<ChartTooltip />}
                cursor={{
                  stroke: 'rgb(240 238 245 / 0.18)',
                  strokeDasharray: '4 4',
                  strokeWidth: 1,
                }}
              />
              {view === 'total' ? (
                <>
                  {/* Glow layer — translucent thicker stroke behind the crisp line. */}
                  <Line
                    type="monotone"
                    dataKey="total"
                    name="Total"
                    stroke="#5EEAD4"
                    strokeOpacity={0.35}
                    strokeWidth={6}
                    dot={false}
                    isAnimationActive={false}
                    activeDot={false}
                    legendType="none"
                  />
                  <Area
                    type="monotone"
                    dataKey="total"
                    name="Total"
                    stroke="#5EEAD4"
                    strokeWidth={1.75}
                    fill="url(#totalFill)"
                    isAnimationActive={false}
                    activeDot={{ r: 5, fill: '#5EEAD4', stroke: '#0f0e14', strokeWidth: 2 }}
                  />
                </>
              ) : (
                assets.map((asset) => (
                  <Line
                    key={asset}
                    type="monotone"
                    dataKey={asset}
                    name={asset}
                    stroke={colorForAsset(asset)}
                    strokeWidth={1.75}
                    dot={false}
                    isAnimationActive={false}
                    activeDot={{ r: 4, fill: colorForAsset(asset), stroke: '#0f0e14', strokeWidth: 2 }}
                  />
                ))
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Sanity-check the build**

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npm run build
```
Expected: build succeeds. (`ChartCard` is not yet imported anywhere, so it tree-shakes; that's fine — Task 9 wires it in.)

- [ ] **Step 5: Commit and push**

```bash
git add frontend/src/components/ChartCard.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add ChartCard — combined balance hero + range pills + chart (/impeccable)

Replaces the previous SummaryBar + PortfolioLineChart pair with a single
trading-terminal-style card. Teal gradient line with translucent glow
layer, dashed crosshair on hover, custom tooltip card, range-relative
delta chip beside the balance hero. Per-asset mode drops the gradient
fill and renders one line per asset using the shared assetColors palette.

Not yet wired into Dashboard — that happens in the layout task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 8: Frontend — rewrite `AssetBreakdown`

**Files:**
- Modify: `.claude/worktrees/tax-hub-foundation/frontend/src/components/AssetBreakdown.tsx` (full rewrite)

- [ ] **Step 1: Invoke `/impeccable` for the visual implementation**

Brief: "Asset breakdown card that replaces a flat dark-grey table. Layout:
1. Card header — `Asset Breakdown` heading.
2. AllocationStackBar — renders directly underneath the heading.
3. Per-asset rows — vertical stack, each row a flex layout with: identity (coloured dot + symbol in mono), holdings (qty + price, two-line stacked), Sparkline (~120×28 of value_aud over filtered range), value (large mono), allocation %, P&L chip in profit/loss tones with up/down arrow.
Sort rows by allocation desc. Hide cost basis (currently $0 across the board). Use the existing surface tokens (bg-surface-raised, border-surface-border, txt-primary/secondary/muted) — no `bg-gray-800`."

- [ ] **Step 2: Implement the rewrite**

Replace `frontend/src/components/AssetBreakdown.tsx` entirely with:

```tsx
import { ArrowDown, ArrowUp } from 'lucide-react'
import type { AssetPosition, PortfolioSnapshot } from '../types'
import { formatAUD, formatPct } from '../utils/pnl'
import { colorForAsset } from '../utils/assetColors'
import AllocationStackBar from './AllocationStackBar'
import Sparkline from './Sparkline'

interface Props {
  positions: AssetPosition[]
  /** Filtered snapshots covering the active range — used for per-asset sparklines. */
  snapshots: PortfolioSnapshot[]
}

function sparklineValues(snapshots: PortfolioSnapshot[], asset: string): number[] {
  return snapshots
    .map((s) => s.assets[asset]?.value_aud)
    .filter((v): v is number => typeof v === 'number')
}

export default function AssetBreakdown({ positions, snapshots }: Props) {
  const sorted = [...positions]
    .filter((p) => p.value_aud > 0)
    .sort((a, b) => b.allocation_pct - a.allocation_pct)

  return (
    <section
      aria-label="Asset breakdown"
      className="bg-surface-raised border border-surface-border rounded-lg p-6"
    >
      <h2 className="text-lg font-semibold text-txt-primary mb-4">
        Asset Breakdown
      </h2>

      <div className="mb-6">
        <AllocationStackBar positions={sorted} />
      </div>

      <ul role="list" className="flex flex-col">
        {sorted.map((p, idx) => {
          const isUp = p.unrealised_pnl_aud >= 0
          const Arrow = isUp ? ArrowUp : ArrowDown
          const tone = isUp
            ? 'bg-profit/10 text-profit'
            : 'bg-loss/10 text-loss'
          return (
            <li
              key={p.asset}
              className={[
                'flex items-center gap-6 py-4 px-2 -mx-2 rounded-md',
                'hover:bg-surface-hover/50 transition-colors',
                idx < sorted.length - 1 ? 'border-b border-surface-border/50' : '',
              ].join(' ')}
            >
              {/* Identity */}
              <div className="w-20 flex items-center gap-2 shrink-0">
                <span
                  aria-hidden="true"
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: colorForAsset(p.asset) }}
                />
                <span className="text-sm font-mono font-medium text-txt-primary">
                  {p.asset}
                </span>
              </div>

              {/* Holdings */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-txt-primary leading-tight">
                  {p.quantity.toFixed(4)} {p.asset}
                </p>
                <p className="text-xs font-mono text-txt-muted leading-tight mt-0.5">
                  @ {formatAUD(p.price_aud)}
                </p>
              </div>

              {/* Sparkline */}
              <div className="w-32 shrink-0">
                <Sparkline
                  values={sparklineValues(snapshots, p.asset)}
                  color={colorForAsset(p.asset)}
                />
              </div>

              {/* Value */}
              <div className="w-28 text-right shrink-0">
                <span className="text-base font-mono font-semibold text-txt-primary">
                  {formatAUD(p.value_aud)}
                </span>
              </div>

              {/* Allocation */}
              <div className="w-16 text-right shrink-0">
                <span className="text-sm font-mono text-txt-muted">
                  {formatPct(p.allocation_pct)}
                </span>
              </div>

              {/* P&L chip */}
              <div className="w-32 text-right shrink-0">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-mono font-medium ${tone}`}>
                  <Arrow className="h-3 w-3" strokeWidth={2.25} />
                  {formatAUD(Math.abs(p.unrealised_pnl_aud))}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
```

- [ ] **Step 3: Sanity-check the build**

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npm run build
```
Expected: build fails because `Dashboard.tsx` still passes only `positions` to `AssetBreakdown` (it now also requires `snapshots`). That gets fixed in Task 9 — proceed.

- [ ] **Step 4: Commit and push**

```bash
git add frontend/src/components/AssetBreakdown.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): rewrite AssetBreakdown with stack bar + per-asset rows (/impeccable)

Replaces the bg-gray-800 <table> with the spec'd layout: AllocationStackBar
on top, then per-asset rows (identity dot + symbol, holdings, Sparkline,
value, allocation, P&L chip). Uses the surface/txt design tokens for
cohesion with the rest of the app. Cost basis intentionally hidden in v1.

Dashboard wiring (the new snapshots prop) lands in the next task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Task 9: Frontend — wire `Dashboard` to the new components, widen layout, delete old files

**Files:**
- Modify: `.claude/worktrees/tax-hub-foundation/frontend/src/pages/Dashboard.tsx`
- Delete: `.claude/worktrees/tax-hub-foundation/frontend/src/components/SummaryBar.tsx`
- Delete: `.claude/worktrees/tax-hub-foundation/frontend/src/components/PortfolioLineChart.tsx`

- [ ] **Step 1: Confirm no other callers of the deleted components**

```bash
cd .claude/worktrees/tax-hub-foundation
grep -rn "SummaryBar\|PortfolioLineChart" frontend/src --include="*.ts" --include="*.tsx"
```
Expected: only `Dashboard.tsx` references either. If anything else does, stop and surface to the user.

- [ ] **Step 2: Rewrite `Dashboard.tsx`**

Replace `frontend/src/pages/Dashboard.tsx` with:

```tsx
import { useState, useEffect, useCallback, useMemo } from 'react'
import { fetchPortfolioSummary, fetchSnapshots, fetchDCAHistory } from '../api/portfolio'
import type { PortfolioSummary, PortfolioSnapshot, DCAEntry } from '../types'
import ChartCard, { type Range } from '../components/ChartCard'
import AssetBreakdown from '../components/AssetBreakdown'
import DCAHistoryTable from '../components/DCAHistoryTable'
import AgentInput from '../components/AgentInput'
import AgentPanel from '../components/AgentPanel'
import { useAgentChat } from '../hooks/useAgentChat'
import { SERVER_ERROR_EVENT, type ServerErrorDetail } from '../api/client'
import ErrorBanner from '../components/ErrorBanner'

interface DashboardErrors {
  summary?: string
  snapshots?: string
  dca?: string
}

interface DashboardState {
  summary: PortfolioSummary | null
  snapshots: PortfolioSnapshot[]
  dcaHistory: DCAEntry[]
  errors: DashboardErrors
}

function errMsg(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '1Y': 365,
  ALL: null,
}

function filterByRange(snapshots: PortfolioSnapshot[], range: Range): PortfolioSnapshot[] {
  const days = RANGE_DAYS[range]
  if (days === null) return snapshots
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - days)
  return snapshots.filter((s) => new Date(s.captured_at) >= cutoff)
}

interface DashboardProps {
  onSignedOut: () => void
}

export default function Dashboard({ onSignedOut: _onSignedOut }: DashboardProps) {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    snapshots: [],
    dcaHistory: [],
    errors: {},
  })
  const [refreshing, setRefreshing] = useState(false)
  const [range, setRange] = useState<Range>('1M')
  const [view, setView] = useState<'total' | 'per-asset'>('total')
  const [panelOpen, setPanelOpen] = useState(false)
  const agent = useAgentChat()
  const [serverError, setServerError] = useState<ServerErrorDetail | null>(null)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const errors: DashboardErrors = {}

    const [summaryResult, snapshotsResult, dcaResult] = await Promise.allSettled([
      fetchPortfolioSummary(),
      fetchSnapshots(),
      fetchDCAHistory(),
    ])

    const summary = summaryResult.status === 'fulfilled' ? summaryResult.value : null
    if (summaryResult.status === 'rejected') errors.summary = errMsg(summaryResult.reason)

    const snapshots = snapshotsResult.status === 'fulfilled' ? snapshotsResult.value : []
    if (snapshotsResult.status === 'rejected') errors.snapshots = errMsg(snapshotsResult.reason)

    const dcaHistory = dcaResult.status === 'fulfilled' ? dcaResult.value : []
    if (dcaResult.status === 'rejected') errors.dca = errMsg(dcaResult.reason)

    setState((prev) => ({
      summary: summary ?? prev.summary,
      snapshots: snapshots.length > 0 ? snapshots : prev.snapshots,
      dcaHistory: dcaHistory.length > 0 ? dcaHistory : prev.dcaHistory,
      errors,
    }))
    setRefreshing(false)
    if (summaryResult.status === 'fulfilled') {
      setServerError(null)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && panelOpen) {
        setPanelOpen(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [panelOpen])

  useEffect(() => {
    function handleServerError(e: Event) {
      const detail = (e as CustomEvent<ServerErrorDetail>).detail
      setServerError(detail)
    }
    window.addEventListener(SERVER_ERROR_EVENT, handleServerError)
    return () => window.removeEventListener(SERVER_ERROR_EVENT, handleServerError)
  }, [])

  function handleAgentSubmit(content: string) {
    setPanelOpen(true)
    agent.send(content)
  }

  const { summary, snapshots, dcaHistory, errors } = state
  const filteredSnapshots = useMemo(
    () => filterByRange(snapshots, range),
    [snapshots, range],
  )
  const hasAnyError = Boolean(errors.summary || errors.snapshots || errors.dca)
  const hasAnyData = summary !== null || snapshots.length > 0 || dcaHistory.length > 0

  return (
    <div className="flex min-h-screen bg-surface text-txt-primary font-sans">
      <main className="flex-1 min-w-0">
        {/* Agent input pill — top right */}
        <div className="px-8 pt-6">
          <div className="w-full max-w-[1600px] mx-auto flex items-center justify-end">
            <div className="border border-surface-border rounded-md px-3 py-1.5 hover:border-kraken/50 transition-colors">
              <AgentInput
                onSubmit={handleAgentSubmit}
                onFocus={() => setPanelOpen(true)}
                panelOpen={panelOpen}
              />
            </div>
          </div>
        </div>

        {/* Server error banner (5xx) */}
        {serverError && (
          <ErrorBanner
            detail={serverError}
            onRetry={() => {
              setServerError(null)
              refresh()
            }}
            onDismiss={() => setServerError(null)}
          />
        )}

        {/* Stale-data banner */}
        {hasAnyError && hasAnyData && (
          <div
            className="bg-loss/10 border-b border-loss/20 px-8 py-2 text-sm text-loss"
            role="alert"
            aria-live="polite"
          >
            <div className="w-full max-w-[1600px] mx-auto flex items-center justify-between">
              <span>Refresh failed — showing cached data.</span>
              <button
                type="button"
                onClick={refresh}
                disabled={refreshing}
                className="px-3 py-1 bg-loss/20 hover:bg-loss/30 active:scale-[0.97] disabled:opacity-50 text-loss rounded text-xs font-medium transition-[colors,transform]"
              >
                {refreshing ? 'Retrying…' : 'Retry'}
              </button>
            </div>
          </div>
        )}

        {/* Main content */}
        <div className="w-full max-w-[1600px] mx-auto px-8 pt-6 pb-16 space-y-6">
          <ChartCard
            summary={summary}
            snapshots={filteredSnapshots}
            range={range}
            onRangeChange={setRange}
            view={view}
            onViewChange={setView}
            onRefresh={refresh}
            refreshing={refreshing}
            summaryError={errors.summary}
            snapshotsError={errors.snapshots}
          />

          {summary ? (
            <AssetBreakdown positions={summary.positions} snapshots={filteredSnapshots} />
          ) : errors.summary ? (
            <div className="text-base text-loss bg-surface-raised border border-surface-border rounded-lg p-6" role="status" aria-live="polite">
              Assets unavailable: {errors.summary}
            </div>
          ) : (
            <div className="text-base text-txt-muted bg-surface-raised border border-surface-border rounded-lg p-6 animate-pulse">
              Loading…
            </div>
          )}

          {/* DCA history */}
          <div className="border-t border-surface-border pt-10">
            {dcaHistory.length > 0 ? (
              <DCAHistoryTable entries={dcaHistory} />
            ) : errors.dca ? (
              <div className="text-base text-loss" role="status" aria-live="polite">
                DCA history unavailable: {errors.dca}
              </div>
            ) : (
              <div className="text-base text-txt-muted">
                No DCA history yet. Sync your Kraken trades to see purchase history.
              </div>
            )}
          </div>
        </div>
      </main>

      {panelOpen && (
        <AgentPanel
          messages={agent.messages}
          activeTools={agent.activeTools}
          hitl={agent.hitl}
          thinking={agent.thinking}
          onRespondHITL={agent.respondHITL}
          onNewConversation={agent.newConversation}
          onSubmit={handleAgentSubmit}
        />
      )}
    </div>
  )
}
```

Key changes versus the previous Dashboard:
- `Range` is now imported from `ChartCard` (no more `'6M'` because it was unused in practice).
- Removed `SummaryBar` import + render path; the chart card carries the balance hero.
- `AssetBreakdown` receives the `filteredSnapshots` for sparklines.
- Outer wrapper is `w-full max-w-[1600px] mx-auto px-8` (replaces `max-w-7xl mx-auto px-6`).
- The `space-y-6` replaces the old `pb-12` rhythm.
- The conditional skeleton chrome on the loading/error states uses the same card chrome as the real components for visual continuity.

- [ ] **Step 3: Delete the obsolete components**

```bash
cd .claude/worktrees/tax-hub-foundation
git rm frontend/src/components/SummaryBar.tsx frontend/src/components/PortfolioLineChart.tsx
```

- [ ] **Step 4: Build and typecheck**

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npm run build
```
Expected: build succeeds, no TypeScript errors. If a stray `Range` import (with the old `'6M'`) breaks something, search for it and update.

- [ ] **Step 5: Visually verify in the browser**

Make sure the backend is running with the Task 1 fix in place and the snapshots have been re-backfilled (Task 1 Step 7). Then:

```bash
cd .claude/worktrees/tax-hub-foundation/frontend && npm run dev
```

Open the app, log in, and check:
- Layout fills the screen up to ~1600px (no awkward right-half emptiness on a 1920×1080+ monitor).
- Balance hero shows the correct AUD value with delta chip in the active range.
- Range pills filter both the chart and every breakdown sparkline together.
- Total view: smooth teal gradient line, hover crosshair + tooltip card, refresh icon spins on click.
- Per-asset view: 4 lines (ETH teal, SOL violet, ADA blue, LINK cyan), all four legend dots present.
- Asset breakdown: stacked allocation bar at the top with hover tooltips, four rows below in allocation order, sparklines visible per asset.
- No spike/dip in the chart history.
- DCA table still renders below.

If anything looks off, fix in this commit before proceeding.

- [ ] **Step 6: Commit and push**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/components/SummaryBar.tsx frontend/src/components/PortfolioLineChart.tsx
git commit -m "$(cat <<'EOF'
feat(dashboard): wire ChartCard + redesigned AssetBreakdown, widen layout to 1600px

Replaces SummaryBar + PortfolioLineChart with the unified ChartCard,
threads filteredSnapshots through to AssetBreakdown for per-asset
sparklines, widens the content cap from max-w-7xl (1280px) to
max-w-[1600px] so the dashboard fills wide screens cleanly behind
the SideRail. Drops the obsolete component files.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
git push
```

---

## Self-review notes

**Spec coverage:**
- §1 Goal — covered across all tasks.
- §2 Architecture / state flow — Task 9 (single `range` source of truth in Dashboard, removed from chart).
- §3 New / modified / deleted files — every entry has a task.
- §4.1 Balance hero row — Task 7.
- §4.2 Controls row — Task 7.
- §4.3 Chart (gradient, glow, hover, custom tooltip, per-asset palette, key union) — Task 7 + Task 6 (key union).
- §4.4 AssetBreakdown — Tasks 5, 8.
- §4.5 Layout widening + empty-state behaviour — Task 9.
- §5 Behaviour and edge cases — Task 4 (sparkline N=0/1), Task 6 (range delta), Task 7 (refresh icon spin, last-updated formatting), Task 9 (skeleton chrome).
- §6 Backend bug fix detail + verification — Task 1.
- §7 Testing — Task 1 unit test + manual smoke in Task 9 Step 5.
- §8 Trade-offs — informational; no task needed.
- §9 Open questions — none, no task needed.

**Type / signature consistency:**
- `Range` defined in `ChartCard.tsx` Task 7 as `'1W' | '1M' | '3M' | '1Y' | 'ALL'`; imported in `Dashboard.tsx` Task 9 with the same union.
- `AssetBreakdown` props in Task 8 are `{ positions, snapshots }`; Dashboard Task 9 passes both.
- `colorForAsset` defined in Task 3, consumed in Tasks 5, 7, 8 with matching signature `(asset: string) => string`.
- `unionAssetKeys` and `computeRangeDelta` defined in Task 6, consumed in Task 7 with matching signatures.

**Placeholder scan:** none.

---

## After all tasks

The spec's manual verification checklist (§7) should be re-run end-to-end on the live app. If the chart dip is still visible after Task 1's backfill rerun, surface the snapshot dump immediately — there may be additional unmapped ledger codes (e.g. for ADA/SOL bonded variants) that surfaced once the ETH fix unblocked them. The fix pattern is identical: add the code to `ASSET_MAP[<asset>]["keys"]` and re-run backfill.
