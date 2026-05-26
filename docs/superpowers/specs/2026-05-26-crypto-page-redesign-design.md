# Crypto Page Redesign — Tabbed Layout + Dedicated AI Chat

**Date:** 2026-05-26
**Scope:** `frontend/src/pages/CryptoPage.tsx` and the components it composes. No other top-level page (Combined, UP Bank, Strategies) changes.

## Problem

The current Crypto page stacks every section on one long scrolling surface (Balance card + chart + Asset Breakdown + DCA History), with the AI chat squeezed into a ~384px right rail and an `AgentInput` jammed into the top bar next to Sign out. The result:

- The chat surface is too narrow; agent replies (especially tables) wrap awkwardly and look cramped.
- Markdown tables emitted by the agent (e.g. asset snapshots) render as raw `| Asset | Qty | Price | … |` pipe text because `react-markdown` is loaded without a GFM plugin.
- DCA History does not update automatically — there is no scheduled Kraken trade sync, only a manual `POST /api/sync` endpoint. New buys do not appear until that endpoint is called.
- The "DCA History" label is confusing. The user thinks of these as "previous purchases" — a flat list of trades.

## Goals

1. Split the Crypto page into four focused tabs so each piece of context gets full width.
2. Give the AI chat a dedicated, conversational surface — hero on empty, standard chat once a conversation starts.
3. Render markdown faithfully — tables, headings, lists, bold, inline code, code fences, blockquotes — styled to match the project's dark theme.
4. Make new Kraken purchases visible in the "Previous Purchases" tab without restarting anything: a manual "Sync now" button.

## Out of scope

- Combined, UP Bank, Strategies pages — untouched.
- Scheduling an automatic Kraken trade sync (user picked manual-only for now; can be added later via `backend/scheduler.py`).
- Any change to the LangGraph agent, websocket protocol, or backend tools.
- Sidebar nav structure — stays as `Combined / Crypto / UP Bank / Strategies`.

## High-level structure

```
┌─ Sidebar ─┬──────────────────────────────────────────┐
│ Combined  │                              Sign out    │
│ ▶ Crypto  ├──────────────────────────────────────────┤
│ UP Bank   │ Balance · Asset Breakdown · Previous     │
│ Strategies│ Purchases · Ask AI                       │
│           ├──────────────────────────────────────────┤
│           │                                          │
│           │     (active tab content only)            │
│           │                                          │
└───────────┴──────────────────────────────────────────┘
```

- Sidebar unchanged.
- Top bar collapses to just `<SignOutButton>`; the global `<AgentInput>` and right-rail `<AgentPanel>` are removed.
- A new horizontal tab bar sits inside the existing `max-w-[1600px]` content container directly under the top bar.
- Active tab is stored in URL search-param `?tab=balance|assets|purchases|ask` so refresh and back-button preserve state. Default = `balance`.

### Tab bar styling

- Underline-style tabs: text labels with a 2px bottom border that animates between active tabs.
- Active label colour: `text-txt-primary` + `border-kraken` (the existing kraken purple `#7B61FF`).
- Inactive labels: `text-txt-muted` with `hover:text-txt-secondary`.
- 1px `border-surface-border` bottom rule across the full width below the labels, with the active underline punching through it.
- Tab labels: `Balance`, `Asset Breakdown`, `Previous Purchases`, `Ask AI`.

## Tabs

### Balance

- Existing `<ChartCard>` component as-is, given the page width.
- Existing range pills (`1W / 1M / 3M / 1Y / ALL`) and view toggle (`Total / Per asset`) — no change.
- Last-updated timestamp + refresh icon stay on the card.

### Asset Breakdown

- Existing `<AssetBreakdown>` component, full width.
- No structural change; the component already shows allocation bar + per-asset rows with sparklines and P&L chips.

### Previous Purchases

- Renamed from "DCA History". The page header reads **Previous Purchases**.
- Existing `<DCAHistoryTable>` retained but **reduced to five columns**:
  `Date · Asset · Quantity · Buy Price · Cost Paid`.
  Columns removed: `Current Value`, `P&L`. (The user wants this tab to answer "what did I buy and when?", not "where is it now?".)
- Sub-header row inside the tab containing:
  - Left: short caption — "All purchases synced from Kraken."
  - Right: **Sync now** button.
- Layout: the Sync row sits immediately above the table card (not inside it). Left: short caption; right: button + last-sync timestamp.
- Sync flow:
  1. Button click → `POST /api/sync` via `apiFetch`.
  2. While in-flight: button disabled, label changes to "Syncing…", spinner icon.
  3. On success: read `synced` count from response body (`{"synced": N, "last_trade_id": …}`); refetch `/api/history/trades`; show inline status `Synced N new purchases · just now` for 5s before fading to a static `Last synced HH:MM`.
  4. On error: inline status in `text-loss` with `err.message`; button re-enabled.
- Empty state (no entries yet): centered placeholder "No purchases recorded yet. Click Sync now to pull from Kraken."

### Ask AI

Dedicated chat surface. Owns `useAgentChat`. Has two states driven by `messages.length`:

#### Empty state (`messages.length === 0`)

- Centered column, max-width ~640px, vertical-centered within the tab pane.
- Sparkles icon at top (kraken-purple) in a subtle rounded square `bg-kraken/10 p-3 rounded-2xl`.
- Headline: **How can I help with your portfolio?** (font-semibold, text-3xl).
- Subtitle: "Ask anything about your holdings, P&L, or recent purchases." (text-txt-muted, text-base).
- Large rounded-full prompt input bar (`AgentInput` variant `hero`):
  - `bg-surface-raised` background, `border-surface-border` ring, focus ring `ring-kraken/40`.
  - Sparkles icon on the left, Enter-hint chip on the right.
  - Placeholder "Ask anything…".
- Four suggestion pills below the input:
  1. *Is my portfolio good?*
  2. *What's my biggest holding?*
  3. *Show my recent purchases*
  4. *Am I up this month?*
  Clicking a pill submits the question immediately (calls `agent.send(text)`).
- Subtle backdrop: two absolutely-positioned divs behind the content, each `w-[420px] h-[420px] rounded-full blur-3xl opacity-30` — one `bg-kraken` top-right, one `bg-accent` bottom-left. Container is `relative overflow-hidden` so they don't leak. No Hero1-style blue gradient slabs.

#### Active state (`messages.length > 0`)

- Centered conversation column, max-width ~720px.
- Vertical stack with `space-y-6`:
  - **User messages**: muted small-caps "You" label + body text. No bubble chrome.
  - **Assistant messages**: rendered through the updated `<AgentMessage>` (markdown, see below).
  - **Tool-status chips**: inline above the answer they describe, using the existing `<AgentToolStatus>` look (`🔧 get_my_portfolio · 240ms`).
  - **HITL prompt**: when `hitl.pending`, render `<AgentHITL>` inline between messages — keeps approval gating intact.
- Streaming cursor preserved: existing `bg-txt-muted animate-pulse-subtle` block.
- Input bar docked at the bottom of the tab pane (`AgentInput` variant `docked`), same styling as hero variant but without the giant text above.
- "New conversation" subtle ghost button in the top-right of the `<AskTab>` pane, aligned with the tab bar baseline (only visible when `messages.length > 0`). Calls `agent.newConversation()`, which clears local state and reconnects the WS without a session_id (existing `NewConversationButton` behaviour).

## Markdown rendering (Ask AI)

The agent emits markdown freely — tables, headings, bold, lists, inline code, fenced code blocks, blockquotes. Currently `<Markdown>` is configured **without `remark-gfm`**, so:

- Pipe-table syntax renders as raw pipe text.
- Strikethrough does not render.
- Autolinks do not work.
- Task lists do not render.

### Required changes to `frontend/src/components/AgentMessage.tsx`

1. Install and add `remark-gfm` to the `<Markdown>` `remarkPlugins` prop. (`remark-gfm` is the canonical companion plugin for `react-markdown` v10.)
2. Style every common markdown construct via the `components` map, matched to the project theme:

| Construct | Styling rule |
|---|---|
| `p` | `text-[15px] leading-relaxed text-txt-primary my-3 first:mt-0 last:mb-0` |
| `h1` | `text-2xl font-semibold text-txt-primary mt-6 mb-2` |
| `h2` | `text-xl font-semibold text-txt-primary mt-6 mb-2` |
| `h3` | `text-base font-semibold text-txt-primary mt-4 mb-1` |
| `strong` | `font-semibold text-txt-primary` |
| `em` | `italic text-txt-secondary` |
| `ul` / `ol` | `my-3 pl-5 space-y-1` (`list-disc` / `list-decimal`) |
| `li` | `text-[15px] leading-relaxed text-txt-primary` |
| `a` | `text-kraken hover:underline` |
| `blockquote` | `border-l-2 border-surface-border pl-3 text-txt-secondary italic my-3` |
| `code` (inline) | `px-1 py-0.5 rounded bg-surface-raised text-[13px] font-mono text-accent` |
| `pre code` (fenced) | `block bg-surface-raised border border-surface-border rounded-md p-3 overflow-x-auto text-[13px] font-mono text-txt-primary my-3` |
| `hr` | `border-surface-border my-4` |
| `table` | `w-full text-sm font-mono tabular-nums border-collapse my-3 rounded-md overflow-hidden` |
| `thead` | `bg-surface-raised` |
| `th` | `text-left text-xs uppercase tracking-wider text-txt-muted font-medium px-3 py-2 border-b border-surface-border` |
| `tr` | `border-b border-surface-border/60 last:border-b-0` |
| `td` | `text-sm text-txt-primary px-3 py-2 tabular-nums` |

3. The existing `typeof message.content === 'string' ? message.content : ''` guard (added in commit `e432148`) stays — defence in depth.
4. Keep the streaming cursor.

### Verification

After implementation, ask the agent a question that exercises every construct. The agent has tools that emit tables; "show me a snapshot of my portfolio" will produce a markdown table. The fix is verified when:

- The pipe-table syntax renders as a styled HTML table with dark header, alternating-row treatment, and right-aligned numeric columns.
- Bold, italic, headings, lists, and inline code all show distinct styling.
- Code fences render with a code-block background.

## Files

### New
- `frontend/src/components/crypto/CryptoTabBar.tsx` — underline tab bar wired to URL search-param.
- `frontend/src/components/crypto/BalanceTab.tsx`
- `frontend/src/components/crypto/AssetsTab.tsx`
- `frontend/src/components/crypto/PurchasesTab.tsx` — wraps `DCAHistoryTable` (reduced columns) + Sync-now button.
- `frontend/src/components/crypto/AskTab.tsx` — owns `useAgentChat`, renders hero or conversation state.
- `frontend/src/components/AgentConversation.tsx` — vertical message stack (user + assistant + tool chips + HITL).
- `frontend/src/components/SuggestionPills.tsx` — 4 pill buttons.

### Modified
- `frontend/src/pages/CryptoPage.tsx` — becomes a thin host: data fetch (`useCryptoData` hook extracted from the current `refresh` logic) + tab router + sign-out button. Loses inline `AgentInput` and `AgentPanel`.
- `frontend/src/components/DCAHistoryTable.tsx` — drop `Current Value` and `P&L` columns; rename heading (or drop the inline heading since the tab title carries the label); migrate styling from raw `bg-gray-800` / `gray-700` to project tokens (`bg-surface-raised`, `border-surface-border`, etc.).
- `frontend/src/components/AgentMessage.tsx` — add `remark-gfm`, add full component-map styling listed above.
- `frontend/src/components/AgentInput.tsx` — accept a `variant?: 'hero' | 'docked'` prop and adjust width / icons / hints accordingly; keep the existing focus behaviour.

### Removed from CryptoPage (but components themselves stay in repo, in case another page uses them later)
- `<AgentPanel>` usage in `CryptoPage.tsx`.

### Dependencies
- Add `remark-gfm` to `frontend/package.json`.

## Data flow

- `useCryptoData()` (extracted from current `CryptoPage` `refresh` logic) returns `{ summary, snapshots, dcaHistory, errors, refreshing, refresh }`. CryptoPage owns this hook; each tab reads what it needs via props. This keeps a single source of truth and means switching tabs doesn't refetch.
- `useAgentChat()` lives only inside `<AskTab>`. WebSocket connection initiates when the Ask AI tab mounts; it persists while the tab is open. Switching to another tab unmounts the AskTab — that closes the WS, which is fine because the LangGraph checkpointer + session-id in localStorage allow seamless rehydration when the user returns. (We already fixed the rehydration crash in commit `e432148`.)
- Sync button on Previous Purchases: local React state inside `<PurchasesTab>` for the sync-status badge. After success, it calls back into `useCryptoData` to re-run the DCA fetch.

## Error handling

- Tab content errors stay scoped to their tab. E.g. if `/api/portfolio/summary` fails, the Balance and Asset Breakdown tabs render an `<ErrorBanner>` inside their own pane; the Ask AI tab still works.
- The global `ErrorBoundary` added in commit `c443185` continues to catch any render crash — so a future malformed markdown payload (or anything else) shows a recoverable message instead of a black void.
- 401 still triggers the existing `UNAUTHORIZED_EVENT` → auth state machine → Login page.

## Testing

- **Manual smoke** in browser:
  1. Open `/crypto` — Balance tab loads, chart renders.
  2. Switch through every tab — content swaps, URL `?tab=` updates, refresh preserves selection.
  3. On Previous Purchases, click "Sync now" — button disables, status appears, table re-renders.
  4. On Ask AI: empty state renders. Click a suggestion pill — message sends, surface flips to conversation. Ask "show me a snapshot of my portfolio" — verify table renders styled (not raw pipes), bold and headings render.
  5. Open DevTools network tab during chat — confirm WS `/api/agent/chat` opens once, no crash on rehydration if you reload.
- **Type-check**: `npx tsc --noEmit` in `frontend/` is clean.
- **Existing tests**: `frontend/src/hooks/useAgentChat.test.ts` and `useUpSyncStatus.test.tsx` still pass.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Switching tabs unmounts `useAgentChat` and tears down the WS each time | Acceptable — rehydration is already fixed and fast (Postgres checkpointer). Could be re-evaluated later if it feels slow. |
| Extracting `useCryptoData` introduces a regression in the existing Balance card | Diff the new hook against the current `refresh()` logic in `CryptoPage.tsx`; behaviour should be identical. |
| `remark-gfm` version conflict | `remark-gfm@4` is the v10-compatible release; pin to that. |
| URL `?tab=` value not validated | Use a typed union + fallback to `balance` if unknown — never throw. |

## Non-changes (called out so they don't drift later)

- The LangGraph agent, backend `/api/agent/chat` WS, and `extract_messages` flatten logic are untouched.
- The fix for Markdown crashing on list-content (commits `c443185` and `e432148`) remains in place.
- No backend changes other than the existing `POST /api/sync` being called by the new button.
- No new sidebar items.

## Anti-slop discipline (skills routing)

This redesign will be executed through a chain of skills explicitly chosen against AI-design tells, in this order:

1. **`redesign-existing-projects`** — primary driver. Audit-first scan of the current Crypto page against its checklist (typography, colour/surfaces, layout, interactivity, content). The audit findings inform the implementation tasks before any code is written.
2. **`impeccable craft`** — project's standing rule for frontend work. Generates component code that's aware of the existing design tokens in `frontend/tailwind.config.js` (kraken/accent/surface/txt families).
3. **`design-taste-frontend`** — applied as discipline only (its brief excludes dashboards). The relevant rules: state the "design read" up front, avoid AI-purple gradient defaults, no centered-hero-over-mesh, no three-equal-card rows, no Inter+slate-900.
4. **`critique`** — after the build, run the persona-based + anti-pattern critique to catch any remaining slop.
5. **`polish`** — final alignment / spacing / micro-detail pass before commit.

### Design read (declared up front, per `design-taste-frontend` §0.B)

*"Reading this as: an existing data-rich crypto portfolio dashboard for a single technical user, with a Linear-style restrained product language, leaning toward the project's existing dark surface tokens + kraken-purple accent + accent-teal highlight. Dials: VARIANCE 5, MOTION 4, DENSITY 5 (dashboard preset, not landing-page maximal)."*

### Explicit anti-patterns banned for this work

Cribbed from the audit skills, narrowed to ones that genuinely apply to a dashboard:

- AI-purple gradient mesh as decoration. The radial blurs behind the Ask AI empty state are subtle (`opacity-30` `blur-3xl`) and use the project's existing tokens, not generic AI purple.
- Three-equal feature-card row. The four tabs are not card-grids; they're underline tabs.
- Pure `#000000` backgrounds. Already using `#0f0e14` surface — keep.
- Browser-default fonts. Evaluate adding `Geist` as the body font during implementation (Inter is also banned per the audit; we currently use neither but the default may resolve to a stack we want to override). Decision deferred to implementation.
- Generic `box-shadow` on cards. Use tinted, low-opacity shadows that respect the surface hue (e.g. `shadow-[0_1px_0_0_rgba(255,255,255,0.04)_inset,0_8px_24px_-12px_rgba(123,97,255,0.25)]`).
- Hollow microcopy ("Lorem ipsum", generic placeholder names). All copy in this redesign is honest and specific to the user's data.
- Empty states that are just blank. The Previous Purchases empty state and Ask AI empty state are both composed.
- Symmetrical 50/50 vertical padding. Bottom padding slightly larger than top for optical balance.
- Instant transitions. All interactive elements get a 200ms ease.

## Implementation order

1. Extract `useCryptoData` hook (no behaviour change yet) — verify Balance still works.
2. Build `<CryptoTabBar>` + URL search-param wiring.
3. Split `BalanceTab`, `AssetsTab`, `PurchasesTab` (move existing content; thin shells around existing components).
4. Add `remark-gfm` + new component-map styling to `<AgentMessage>`.
5. Build `<AgentConversation>`, `<SuggestionPills>`, `<AskTab>` empty + active states.
6. Tighten `<AgentInput>` with the variant prop.
7. Drop top-bar `<AgentInput>` and `<AgentPanel>` from `CryptoPage`.
8. Migrate `<DCAHistoryTable>` column set + theme tokens.
9. Add Sync-now button + status UX inside `<PurchasesTab>`.
10. Smoke-test the whole flow; type-check; commit.
