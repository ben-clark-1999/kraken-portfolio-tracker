# Dashboard Redesign — Design Spec

**Date:** 2026-04-27
**Status:** Approved (pending implementation plan)
**Scope:** Redesigns the authenticated dashboard's chart card and asset breakdown to a polished "instrument-grade" aesthetic, fixes a backend backfill bug that was causing misleading dips in the portfolio chart, and removes the layout cap that was leaving the right half of wide screens empty after the SideRail was added.

---

## 1. Goal

The authenticated dashboard currently sits inside a 1280px column on what is otherwise a wide screen, uses stock Recharts/`bg-gray-800` styling that does not share a vocabulary with the rest of the app (sidebar, login), and renders a portfolio chart whose values are wrong — every backfilled snapshot has `ETH=0` because the bonded ledger code `XETH.B` is unmapped. The result is a dashboard that looks unfinished and shows misleading data.

This redesign fixes all three problems in one pass:

- **Visual quality:** The chart card and asset breakdown are restyled to match the polish of the SideRail and Login (gradient fills, glow, hover crosshair, sparklines, stacked allocation bar).
- **Data accuracy:** The `XETH.B` ledger code is added to the asset map; the snapshots table is wiped and rebuilt so historical values reflect the user's real ETH balance.
- **Layout:** The Dashboard fills the available column up to a sensible ultrawide cap.

**Aesthetic direction:** Hybrid — kraken-violet brand chrome (sidebar, login, app accents stay as they are) with a teal/cyan accent scoped to the chart and breakdown so the dashboard reads as the focal "trading terminal" surface within an otherwise violet app.

**Out of scope for this spec:**
- Touching the SideRail, Login, or any non-dashboard surface
- Touching the Tax Hub
- Cost-basis backfill or any change to lots tracking
- Adding new ranges (1d, 24h, intraday) — the data is hourly snapshots and we do not pretend otherwise
- Sortable columns or asset-row drill-downs (4 assets — YAGNI)
- New API endpoints — the existing `/api/portfolio/summary`, `/api/history/snapshots`, and `/api/history/backfill?clear=true` cover everything

## 2. Architecture

The dashboard becomes a clean three-row stack inside the existing `<main>` column to the right of the SideRail:

```
ChartCard          (replaces SummaryBar + PortfolioLineChart)
AssetBreakdown     (rewritten — stacked allocation bar + per-asset rows with sparklines)
DCAHistoryTable    (unchanged)
```

`SummaryBar` is deleted; its responsibilities (portfolio value hero, last-updated timestamp, refresh button, range pills) move into `ChartCard`'s header.

State flow:

- `Dashboard` owns a single `range: '1W' | '1M' | '3M' | '1Y' | 'ALL'`. Default `1M`.
- `Dashboard` computes `filteredSnapshots` once, hands it to both `ChartCard` and `AssetBreakdown` along with the raw `range` value.
- `ChartCard` exposes the active range visually but does not own its own `range` state — the existing internal `range` state on `PortfolioLineChart` is removed (today it shadows Dashboard's, with overlapping filter logic).
- `AssetBreakdown`'s sparklines render from the same `filteredSnapshots`, so flipping the range zooms both the main chart and every sparkline together. This is what makes the breakdown's sparklines feel like part of the same instrument rather than a separate widget.

No new backend routes. No new database columns. No new dependencies on the frontend (Recharts already covers everything we need; the gradient/glow are SVG `<defs>` inside the existing chart).

## 3. Components and file layout

### New frontend files

| File | Purpose |
|---|---|
| `frontend/src/components/ChartCard.tsx` | The redesigned portfolio chart card. Owns the balance hero row, range pills, total/per-asset toggle, and the chart itself. Replaces `SummaryBar` + `PortfolioLineChart` as a single component. |
| `frontend/src/components/Sparkline.tsx` | Tiny inline line chart, no axes/labels. Used inside each `AssetBreakdown` row. ~120×28px. |
| `frontend/src/components/AllocationStackBar.tsx` | The full-width stacked horizontal bar at the top of `AssetBreakdown`. One segment per asset, hover lifts and shows tooltip. |
| `frontend/src/utils/assetColors.ts` | Single source of truth for per-asset colours (ETH=teal, SOL=violet, ADA=blue, LINK=teal-2). Imported by `ChartCard`, `AllocationStackBar`, `Sparkline`, and `AssetBreakdown`. |

### Modified frontend files

| File | Change |
|---|---|
| `frontend/src/pages/Dashboard.tsx` | Remove `max-w-7xl mx-auto` cap. Replace with `w-full px-8 max-w-[1600px] mx-auto`. Render `ChartCard` instead of `SummaryBar` + `PortfolioLineChart`. Keep `AssetBreakdown` and `DCAHistoryTable` as siblings. Owns `range` state once. |
| `frontend/src/components/AssetBreakdown.tsx` | Full rewrite. No longer a `<table>`. Renders `<AllocationStackBar />` then a column of asset rows, each with glyph + symbol, holdings, sparkline, value, allocation %, P&L chip. |
| `frontend/src/components/PortfolioLineChart.tsx` | **Deleted.** Logic moves into `ChartCard`. |
| `frontend/src/components/SummaryBar.tsx` | **Deleted.** Logic moves into `ChartCard`'s header row. |
| `frontend/tailwind.config.js` | Add the chart-accent teal token (e.g. `accent: '#5EEAD4'`, `accent-glow: 'rgba(94, 234, 212, 0.35)'`) so the chart's gradient/glow can reference design tokens rather than raw hex. Final exact teal value picked during implementation against the kraken-violet to ensure adequate contrast. |

### Modified backend files

| File | Change |
|---|---|
| `backend/config/assets.py` | Add `"XETH.B"` to `ASSET_MAP["ETH"]["keys"]` (right after the existing `"ETH.B"` entry). The auto-derived `BALANCE_KEY_TO_DISPLAY` then maps `XETH.B → ETH` and the backfill ledger walk attributes the bonded transfers correctly. |

### One-off operation (not a code change)

After the backend change lands, the snapshots table must be wiped and rebuilt. Trigger via the existing route:
```bash
curl -X POST 'http://localhost:8000/api/history/backfill?clear=true' \
     -H 'Cookie: auth_token=…'
```
The `clear_snapshots` call already logs `Cleared N snapshots from schema=public` (Phase 4 follow-up). After this runs, the chart should render a smooth ~$0.7k → ~$6k arc with no dips. Implementation plan must verify this in the browser before declaring done.

## 4. Visual specification

### 4.1 ChartCard header — top row (the balance hero)

Single row inside the card's top padding zone. Three logical zones, left → middle → right:

- **Left:** small circular icon (kraken-violet at 15% opacity background, kraken-violet glyph) at 28px square. Beside it, the label `Balance` in `text-sm text-txt-muted`. Below that label (or inline, depending on tightness), the number `$6,000.23` in `text-4xl font-bold font-mono text-txt-primary`, with `AUD` in `text-base text-txt-muted` aligned to the baseline.
- **Middle (inline beside balance):** delta chip `+12.4% · 30d` — small rounded pill, green/red surface tint, value computed from `filteredSnapshots[0].total_value_aud` vs `filteredSnapshots[-1].total_value_aud`. **Range-relative:** flips when the user changes the range pill. Hidden if `filteredSnapshots.length < 2`.
- **Right:** `Last updated 8:57 pm` in `text-xs text-txt-muted`, then a refresh icon button (no text label, but `aria-label="Refresh portfolio"`). Refresh icon spins while `refreshing` is true.

### 4.2 ChartCard header — second row (controls)

Single row of pills, left-aligned by default:

- **Range pills:** `1W` `1M` `3M` `1Y` `ALL`. Active pill has `bg-accent/15 text-accent border-accent/30`. Inactive `bg-surface-raised/40 text-txt-muted hover:text-txt-primary`. Removed: the duplicated `7d/30d/all` row that previously rendered inside the chart. Removed: the granular `1s/15m/1h/4h/1d` row from the reference image — we have no intraday data and showing them disabled or fake-functional would be misleading.
- **Vertical hairline divider** (`w-px bg-surface-border`).
- **Total/Per-asset segmented control:** two pills sharing a rounded enclosure. Same active/inactive treatment as range pills.

### 4.3 ChartCard — the chart

Total view (default):
- Single line, `stroke="var(--accent)"` (teal), `strokeWidth={1.75}`.
- SVG `<defs>` contain two filters/gradients:
  - `<linearGradient id="totalFill">`: teal at 22% opacity at the top → 0% at the bottom. Recharts `<Area>` uses this as `fill="url(#totalFill)"`.
  - `<filter id="totalGlow">`: a 4px Gaussian blur on a duplicated stroke, layered behind the crisp line. Optional v1 — can be a translucent second `<Line>` if SVG filter perf is a concern.
- Active dot (`activeDot` prop): 6px radius teal circle with a 12px outer halo at lower opacity.
- Recharts `<Tooltip>` replaced with a custom component. Card chrome: `bg-surface-raised/95 backdrop-blur-sm border border-surface-border rounded-md px-3 py-2 shadow-lg`. Two lines: `$6,123.45` (large mono) + `27 Apr 2026, 8:57pm` (small muted). Pointer-events-none.
- Crosshair: Recharts ships a `cursor` prop on `<Tooltip>`. Render a vertical dashed line at the active x with `stroke-dasharray="4 4" stroke-opacity="0.3"`. Horizontal dashed line at the active y, drawn via a custom layer.
- Y-axis: `tickFormatter` `$Xk` (existing), `tick={{ fontSize: 11, fill: 'rgb(var(--txt-muted))' }}`. Grid lines at `stroke-opacity="0.06"`.
- X-axis: `DD MMM` formatting (e.g. `27 Apr`) for ranges ≥ 7d. No timezone-suffix noise. `tick={{ fontSize: 11, fill: 'rgb(var(--txt-muted))' }}`.

Per-asset view (toggled):
- Gradient fill is **dropped** (stacked area would muddy with 4 lines). Just lines.
- Each asset's line uses the colour from `assetColors.ts`:
  - `ETH` → accent teal
  - `SOL` → kraken violet
  - `ADA` → blue (e.g. `#60A5FA`)
  - `LINK` → teal-2 (e.g. `#22D3EE`)
- The header's balance hero stays put (still shows total). The delta chip continues to reflect total range delta.
- Legend dots (small coloured dots inline in the controls row) replace the previous Recharts `<Legend>` block.
- **Per-asset key union:** `assets = Array.from(new Set(filteredSnapshots.flatMap(s => Object.keys(s.assets))))`. Fixes the LINK-missing-from-legend bug. Recharts handles missing leading data fine — LINK's line just starts on the first snapshot that has it.

### 4.4 AssetBreakdown card

Card chrome shares the same `bg-surface-raised border border-surface-border rounded-lg p-6` as the chart card.

**Header row:** `Asset Breakdown` in `text-lg font-semibold text-txt-primary`, no subtitle.

**Allocation stack bar:** full-width, `h-2.5 rounded-full overflow-hidden`. One inner segment per asset, `flex` row, segment width = `style={{ flex: allocation_pct }}`. 1px gap between segments via `gap-px`. Each segment `bg-{asset-color}` at 100% opacity; on hover, the segment's brightness lifts (`hover:brightness-125`) and a tooltip pops with `ETH · 63.05% · $3,783.18`. The bar gets `mt-4 mb-6` to separate from header and rows.

**Asset rows:** vertical stack, each row is a `flex items-center gap-6 py-4 border-b border-surface-border/50 last:border-b-0 hover:bg-surface-raised/40 transition-colors rounded-md px-2 -mx-2`.

Row zones, left → right:

| Zone | Width | Content |
|---|---|---|
| Identity | `w-20` | Coloured 8px dot in asset's hue + `ETH` in `text-sm font-mono font-medium text-txt-primary` |
| Holdings | `flex-1 min-w-0` | Two stacked lines — `1.1686 ETH` (mono `text-sm text-txt-primary`) above `@ $3,237.37` (mono `text-xs text-txt-muted`) |
| Sparkline | `w-32 h-7` | `<Sparkline>` component, asset-coloured stroke, no fill, no axes, `strokeWidth={1.5}` |
| Value | `w-28 text-right` | `$3,783.18` in `text-base font-mono font-semibold text-txt-primary` |
| Allocation | `w-16 text-right` | `63.05%` in `text-sm text-txt-muted font-mono` |
| P&L chip | `w-32 text-right` | `+$3,783.18` in green/red rounded chip with up/down arrow icon, `bg-profit/10 text-profit` (or loss equivalent) |

**Sort:** by allocation %, descending. Static sort — no interactive sortable headers (4 rows; YAGNI).

**Cost basis:** **hidden in v1.** Currently $0 across the board so it adds noise without information. Add back when cost-basis backfill is real.

### 4.5 Layout

`Dashboard.tsx` wrapper changes:

```tsx
// before
<div className="max-w-7xl mx-auto px-6">…cards…</div>

// after
<div className="w-full max-w-[1600px] mx-auto px-8 space-y-6">…cards…</div>
```

`max-w-[1600px]` keeps a 27" monitor from rendering a 2400px-wide chart that's hard to read. `space-y-6` replaces the per-section `pb-12` paddings.

Empty state behaviour preserved:
- `summary === null && !errors.summary` → ChartCard renders a skeleton state (placeholder pulse on the balance number, empty chart area with a muted "Loading…" centred).
- `summary === null && errors.summary` → ChartCard renders the error state with the existing retry button.
- `snapshots.length === 0` → chart area shows the existing `"No snapshot history yet"` message.

## 5. Behaviour and edge cases

- **Range flipping should be cheap.** `filteredSnapshots` is `useMemo`'d on `[snapshots, range]`. The chart, the per-asset key union, and every sparkline read from the same memoized array. No additional fetches when the range changes — all data is already on the client.
- **Missing leading data for assets added late (LINK).** Recharts' default behaviour for `null`/missing keys in the data array is to break the line. That's correct: we don't want LINK's line to be drawn flat at $0 from `2026-03-26` until the day it was added. Implementation must verify by toggling per-asset on a range that pre-dates LINK's first snapshot.
- **Refresh during a chart-range view.** The existing `refresh()` re-fetches summary/snapshots/dca; the `range` state is preserved across refreshes. The balance hero updates; the delta chip recomputes against the new range bounds.
- **Last-updated time.** Comes from `summary.captured_at`. Format: `8:57 pm` for today, `27 Apr, 8:57 pm` for older. Existing `formatAUD`/date utilities in `utils/` already handle.
- **Refresh icon spin.** Use `animate-spin` while `refreshing` is true. Disable button while spinning.
- **Per-asset toggle while data is partial.** If `filteredSnapshots[0]` doesn't have LINK and the user toggles to Per Asset, LINK's line begins at the first snapshot where it appears. No "missing asset" message; the legend just shows it and the line is short.
- **Breakdown rows with $0 value.** Skip rendering them. Don't show a row for an asset with zero quantity.
- **Sparkline with single data point.** Render a flat line (use the single value as both endpoints). Don't render nothing.
- **Sparkline with zero data points.** Render an empty box (no error). Should not happen in practice once backfill is fixed.

## 6. Backend bug fix detail

`backend/config/assets.py`:

```python
ASSET_MAP: dict[str, dict] = {
    "ETH": {
        "keys": ["XETH", "ETH", "ETH.B", "XETH.B", "ETH.S", "ETH2", "ETH2.S", "ETH.F"],
        #                          ^^^^^^^^ added
        "pair": "ETHAUD",
    },
    …
}
```

Why this works: `BALANCE_KEY_TO_DISPLAY` is auto-derived from `ASSET_MAP[…]["keys"]`. The backfill walks the ledger and looks up each entry's `asset` field via `BALANCE_KEY_TO_DISPLAY.get(asset_code)`. With `XETH.B` mapped to `ETH`, the bonded transfers no longer fall through, and the running ETH balance accumulates correctly.

Why we did not just add a new `LEDGER_ASSET_TO_DISPLAY` row: `ASSET_MAP["ETH"]["keys"]` already covers `ETH.B`. Putting `XETH.B` next to `ETH.B` keeps related ledger codes co-located, which is the maintenance affordance the file is structured around.

**Verification step in the plan.** After the asset-map change and the backfill rerun, query the snapshots table for any post-clear row where `assets->'ETH'->>'value_aud' = '0'` and `assets->'ETH'->>'quantity'::numeric > 0`. The result must be empty.

## 7. Testing

Unit (frontend, Vitest):
- `Sparkline` renders a line with N points, handles N=0/N=1 gracefully.
- `AllocationStackBar` renders one segment per asset with proportional width.
- `assetColors.ts` returns deterministic colours; falls back to a neutral grey for unknown assets.
- `ChartCard` per-asset key union: given snapshots `[{ETH,SOL}, {ETH,SOL,LINK}]`, returns `['ETH','SOL','LINK']`.
- `ChartCard` range-relative delta: given `filteredSnapshots[0].total = 1000` and `filteredSnapshots[-1].total = 1240`, returns `+24%`.

Unit (backend, pytest):
- `BALANCE_KEY_TO_DISPLAY['XETH.B'] == 'ETH'`. Add to existing `tests/test_assets.py` (or wherever `ASSET_MAP` is exercised).

Integration (manual, in-browser, after both backend + frontend land):
1. Re-run backfill via `POST /api/history/backfill?clear=true`. Verify the response payload shows `cleared > 0, created > 0` with no `skipped_no_price` for the ETH-active period.
2. Reload the dashboard. Chart total mode: smooth arc from ~$700 to ~$6000, no dips below $4k after `2026-04-20`.
3. Toggle per-asset. ETH line is the dominant teal line, all 4 assets appear in the legend, LINK's line starts on the date it was added.
4. Range pills: each one filters chart and breakdown sparklines together. Delta chip recomputes.
5. Resize the browser to 2200px wide. Dashboard fills the screen up to ~1600px and stops. No empty right-half on a 1920×1080 monitor.
6. Hover the chart. Crosshair + tooltip card render correctly. Hover a stacked bar segment in the breakdown. Tooltip shows asset + allocation + value.
7. Refresh button: icon spins, then settles, last-updated timestamp advances.

## 8. Trade-offs and risks

- **Deleting `SummaryBar` and `PortfolioLineChart` is a hard cut.** Anyone who imports them elsewhere would break. Quick `grep` shows only `Dashboard.tsx` consumes them — safe to delete.
- **Wiping the snapshots table is destructive.** The current rows are mostly wrong, so the loss is in our favour. Preserved in this spec because the user explicitly approved the wipe in brainstorming.
- **The teal accent introduces a colour the rest of the app does not use.** It is scoped to the dashboard's chart card and breakdown only — sidebar, login, agent panel, and tax hub stay violet. If the colour ever feels jarring against the rest of the app, the swap is a single token change.
- **Recharts SVG filters can pixelate at high DPR or perform poorly on low-end hardware.** Mitigation: implement glow as a translucent second `<Line>` at higher stroke width if `<filter>` perf is bad. Decide during implementation; not blocking.
- **The granular pills (`1s`, `15m`, `1h`, `4h`, `1d`, `1w`) from the reference image are dropped because we only have hourly snapshots.** Adding them as fakes would mislead. If intraday capture is added later, the pills can come back.

## 9. Open questions

None at the time of writing. All design decisions resolved during brainstorming on 2026-04-27.
