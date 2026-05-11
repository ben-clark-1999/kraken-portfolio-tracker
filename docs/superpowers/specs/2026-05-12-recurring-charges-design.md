# Recurring Charges (Subscriptions) — Design

**Date:** 2026-05-12
**Status:** Approved (brainstorming complete; awaiting user review of written spec)

## Goal

Detect recurring outgoing subscriptions (Netflix, Spotify, gym, etc.) from
the existing UP transaction log and surface them on the UP page and to the
agent. No new sync, no new external APIs — pure analysis on data we already
have.

## Scope

**In scope**

- Detect monthly, yearly, weekly, and fortnightly recurring outflows.
- New section on the UP page showing detected subscriptions with monthly
  total + per-subscription detail.
- New REST endpoint and one new MCP tool exposing the same data.
- Agent integration via the existing `cash` classifier category.

**Out of scope**

- Inbound recurring detection (payroll, refunds, scheduled transfers).
- Variable-amount bills (utilities, insurance) — by user choice.
- Quarterly cadence.
- Manual override / hide-and-mark UI (deferred to v2 if needed).
- Persistence layer for detected results (recomputed per request).
- Cancellation memorialisation ("you cancelled X on Y") — silent disappearance.
- Price-change alerts.
- Agent actions ("cancel this for me").

## User-facing decisions (locked)

| Decision | Choice |
|---|---|
| Detection scope | Subscriptions only (predictable monthly/yearly amounts). |
| Cadences | Weekly + fortnightly + monthly + yearly. |
| Surface | New section on UP page (between Spending and Transactions). |
| Manual override | None in v1. Algorithm-only. |
| UI layout | Dense list with hero monthly total (Layout A from mockups). |

## Architecture

Pure-Python heuristic, computed on-demand from the existing
`up_transactions` table. No new database tables, no caching, no scheduler
job. One service module + one REST endpoint + one MCP tool + one frontend
component.

If precision falls short of expectations later, the upgrade paths in order
are: (1) cached results in a new `up_recurring` table refreshed nightly;
(2) LLM augmentation for ambiguous merchant strings.

## Detection algorithm

Implemented in `backend/services/up_recurring_service.py`. Operates on
**outflows only** (`amount_value < 0`) across the entire transaction
history. Step 5 (active filter) is the freshness gate — there is no
artificial lookback window, since restricting to 180 days would make
yearly subscriptions undetectable (they need ≥2 years of history to
appear ≥3 times).

### Step 1 — Normalise the description

A pure function `normalise(description: str) -> str`:

- Lowercase.
- Strip trailing 6–12 digit numeric suffixes (store numbers, terminal IDs).
- Strip card-network prefixes: `SQ *`, `PY *`, `TPG *`, `PAYPAL *`.
- For `ABC *COMPANY` patterns, take the part after the asterisk.
- Collapse whitespace; trim.

The normaliser is the single biggest precision lever. It must be unit-tested
against a fixture of real merchant strings.

### Step 2 — Group by normalised description

A subscription candidate is a group with:

- **≥3 transactions** for sub-yearly cadences (weekly / fortnightly /
  monthly), OR
- **≥2 transactions** for groups whose intervals look yearly.

Cadence is determined first (Step 3) so the threshold can be applied
appropriately. Groups smaller than the threshold for any cadence are
ignored.

### Step 3 — Cadence detection

For each group, sort by date and compute consecutive intervals in days.
Bucket each interval:

| Bucket | Days |
|---|---|
| `weekly` | 7 ± 1 |
| `fortnightly` | 14 ± 2 |
| `monthly` | 28–32 |
| `yearly` | 360–372 |

A group is **recurring** if **≥80% of its intervals fall in the same bucket**.
The dominant bucket becomes its cadence. Groups whose intervals don't
cluster (e.g. a gym with sporadic extra fees) are dropped.

### Step 4 — Amount stability

Compute the median amount across the group. Compute coefficient of variation
(`stddev / median`). Require **CV ≤ 0.15** — a hard cap on jitter.
Subscriptions like Netflix have CV near 0; loose bills (electricity) usually
fail this on purpose.

### Step 5 — Active filter

Drop any group whose most recent charge is older than `2 × cadence_days`
(missed two cycles → probably cancelled).

### Step 6 — Output

Per surviving group, build a `RecurringCharge` containing:

```python
class RecurringCharge(BaseModel):
    name: str                  # title-cased normalised name
    sample_description: str    # one raw example
    cadence: Literal["weekly", "fortnightly", "monthly", "yearly"]
    median_amount: float       # positive (outflow magnitude)
    last_charged_at: datetime
    next_expected_at: datetime
    occurrence_count: int
    monthly_equivalent: float  # cadence-normalised cost
```

`monthly_equivalent` lets the UI show all subs on one comparable scale and
lets the service compute a true total monthly burden.

Output sorted by `monthly_equivalent DESC`.

## REST API

`backend/routers/up.py` gains:

```
GET /api/up/recurring   → list[RecurringCharge]
```

Auth-gated via the existing router-level `require_auth` dependency. No query
parameters in v1.

## Agent surface

### New MCP tool

`backend/mcp_server.py` gains:

```python
@mcp.tool()
def get_recurring_charges() -> str:
    """Detected recurring charges (subscriptions). Returns each subscription's
    cadence, amount, and monthly-equivalent cost, sorted by largest first.
    Includes a total monthly subscription burden at the top."""
```

Output format mirrors the other UP tools — heading line + indented list:

```
Total recurring subscriptions: $487.45/month  (8 active)
  - Spotify         monthly   $11.99   (next: 2026-05-28)
  - Anytime Fitness monthly   $29.95   (next: 2026-06-01)
  - Adobe CC        monthly   $32.99   (next: 2026-06-04)
  - iCloud          yearly    $99.00   (next: 2026-11-12, ~$8.25/mo)
  …
```

### Tool subset + prompt

Extend `TOOL_SUBSETS["cash"]` in `backend/agent/agent_config.py` to include
`"get_recurring_charges"`. Add one bullet to `CASH_APPENDIX` in
`backend/agent/prompts.py` so the agent knows when to reach for it.

No new classifier category. Questions like "what subscriptions am I paying
for?" already classify as `cash`.

## Frontend

### New files

```
frontend/src/components/up/RecurringList.tsx
```

### Modified files

```
frontend/src/api/up.ts          + fetchRecurring()
frontend/src/types/up.ts        + RecurringCharge interface
frontend/src/pages/UpPage.tsx   + new <Section title="Subscriptions">
                                  between Spending and Transactions
```

### Layout (Locked: design A from mockups)

```
SUBSCRIPTIONS                                          8 active
$487.45/mo
total recurring
─────────────────────────────────────────────────────────────
Spotify                                                  $11.99
Monthly · next 28 May                                       /mo
─────────────────────────────────────────────────────────────
Anytime Fitness                                         $29.95
Monthly · next 1 Jun                                        /mo
─────────────────────────────────────────────────────────────
iCloud+                                                   $8.25
Yearly $99.00 · next 12 Nov                            /mo equiv
```

- Hero: monthly total in big mono with secondary count.
- Each row: name (left, primary text), monthly cost (right, mono).
- Below name: cadence + next-charge date in `text-xs text-txt-muted`.
- Yearly subs: right column shows monthly equivalent labelled `/mo equiv`;
  the secondary line shows the actual annual amount.
- Section uses the existing `<Section>` wrapper for border + title rhythm.

### State handling

- Fetched in the same `useEffect` block that loads accounts (independent
  of the range picker — subscriptions are always "what's currently active").
- Loading: same skeleton pattern as other UP sections.
- Empty state: "No recurring charges detected. A subscription needs to
  charge regularly with a stable amount before we can spot it (3 monthly
  charges, or 2 yearly)."

## Edge-case behaviours we accept

- A brand-new subscription doesn't appear until its 3rd charge (~3 months
  for monthly subs). The empty state explains this.
- Apple's umbrella billing (Apple Music + iCloud through one merchant ID)
  may cluster as one "subscription" with weird amount jitter, fail
  CV ≤ 0.15, and be dropped. False negative, not a wrong answer.
- A subscription whose price changed substantially (>15%) breaks the
  cluster temporarily; reappears after 3 charges at the new price.
- Cancellations are silent — the row disappears.

## Testing

| Layer | File | Coverage |
|---|---|---|
| Unit (normaliser) | `backend/tests/test_up_recurring_normaliser.py` | Table of ~15–20 real merchant strings → expected normalised form. Covers store-number suffix, asterisk-prefix card-network noise, whitespace, mixed case. |
| Service | `backend/tests/test_up_recurring_service.py` | Synthetic `UpTransaction` fixtures: 5 monthly Netflix → detected; 3 weekly Audible → detected; 2 yearly iCloud → detected (yearly threshold); 2 monthly charges → NOT detected (below sub-yearly threshold); 5 Coles with high CV → NOT detected (amount stability fails); 4 monthly with last >2 cycles old → NOT detected (active filter); sporadic mixed-cadence cluster → NOT detected (interval consistency fails). |
| Router | `backend/tests/test_up_router.py` | One test for `GET /api/up/recurring` (seed, hit, assert shape). |
| MCP tool | `backend/tests/test_mcp_up_tools.py` | Extend with `get_recurring_charges()` smoke. |
| Frontend | `frontend/src/components/up/RecurringList.tsx` | No formal tests in v1; relies on browser smoke. |

## Performance

Algorithm is O(n) grouping + O(g·k) per-group analysis where `g = group
count` and `k = avg group size`. For 10k transactions and ~50 groups, well
under 50ms locally. No caching needed.

## Migration safety

No schema changes. No data writes. Reverting is `git revert` and zero
operational impact.

## Open questions

None at present — all design decisions resolved during brainstorming.
