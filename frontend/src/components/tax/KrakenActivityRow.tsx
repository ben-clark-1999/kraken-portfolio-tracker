import type { JSX } from 'react'

import type { KrakenFYActivity } from '../../types/tax'

/* ──────────────────────────────────────────────────────────────────────────
 * KrakenActivityRow — read-only crypto activity readout for a single FY.
 *
 * Design rationale: this is the quietest element in an expanded financial
 * year. It is reference data — the user's Kraken buys for the year, drawn
 * from the lots ledger — and exists alongside the three editable EntryLists.
 * The Dashboard owns the "add a buy" flow; this component never offers
 * action of its own. It only reports.
 *
 *   • Slim horizontal row: instrument-panel eyebrow on the left, primary
 *     "X invested · N buys" on the centre line, per-asset chips trailing.
 *     No card silhouette, no add button, no kebab menu — visual weight is
 *     deliberately a notch below the EntryList header that follows it.
 *   • Per-asset chips are pill-shaped hairline-bounded tags with an asset
 *     ticker eyebrow and the AUD spend beneath. Order is largest spend
 *     first so the eye lands on the dominant position. Cap at six chips
 *     and roll the remainder into a "+N more" tag — keeps the strip from
 *     overflowing into a multi-row block on long histories.
 *   • Empty state ("No crypto buys this FY") is a single muted line —
 *     no card, no illustration. The absence of activity is information,
 *     not an error.
 *   • Whole-dollar AUD throughout — cents would be visual noise at a
 *     reference-readout position.
 *
 * No left-edge accent stripes (banned). Mirror the Toast eyebrow language
 * (CRYPTO ACTIVITY, monospaced, 0.22em tracking) so the page reads as one
 * instrument rather than several pasted-together components.
 * ────────────────────────────────────────────────────────────────────── */

interface KrakenActivityRowProps {
  activity: KrakenFYActivity
}

/**
 * AUD whole-dollar formatter, module-scoped — cheap to reuse across many
 * renders, expensive to allocate on every row.
 */
const AUD = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  maximumFractionDigits: 0,
})

/** Chips beyond this count collapse into a "+N more" tag */
const VISIBLE_CHIP_LIMIT = 6

interface PerAssetEntry {
  symbol: string
  audSpent: number
}

/**
 * Sort the per-asset record into a stable, dominant-first list. We don't
 * mutate the record; building a fresh array keeps the render pure and
 * makes React's reconciliation predictable when the data shape shifts.
 */
function sortPerAsset(per: KrakenFYActivity['per_asset']): PerAssetEntry[] {
  return Object.entries(per)
    .map(([symbol, info]) => ({ symbol, audSpent: info.aud_spent }))
    .sort((a, b) => b.audSpent - a.audSpent)
}

export default function KrakenActivityRow({
  activity,
}: KrakenActivityRowProps): JSX.Element {
  const totalBuys = activity.total_buys
  const isEmpty = totalBuys === 0
  const sorted = sortPerAsset(activity.per_asset)
  const visible = sorted.slice(0, VISIBLE_CHIP_LIMIT)
  const overflowCount = Math.max(0, sorted.length - visible.length)

  /* ── Empty state ────────────────────────────────────────────────────────
     A single restrained line — no card, no icon. The absence of buys for
     a given FY is itself informational; padding it into a "no data"
     illustration would over-dramatise an everyday scenario. */
  if (isEmpty) {
    return (
      <section
        aria-label="Kraken activity"
        className={[
          'flex items-center gap-3 px-4 py-3',
          'rounded-[10px] border border-surface-border/60 bg-surface-raised/15',
        ].join(' ')}
      >
        <span
          className={[
            'text-[10px] font-medium tracking-[0.22em] uppercase leading-none',
            'text-txt-muted',
          ].join(' ')}
        >
          Crypto Activity
        </span>
        <span className="h-3 w-px bg-surface-border/70" aria-hidden="true" />
        <span className="text-[12.5px] tracking-tight text-txt-muted">
          No crypto buys this FY
        </span>
      </section>
    )
  }

  /* ── Populated state ──────────────────────────────────────────────────── */
  return (
    <section
      aria-label="Kraken activity"
      className={[
        // Hairline strip — mirrors the silhouette of FYSummaryStrip but a
        // notch quieter (lower-opacity background, no internal cell
        // dividers). The whole row reads as a single readout.
        'flex flex-wrap items-center gap-x-4 gap-y-2.5 px-4 py-3',
        'rounded-[10px] border border-surface-border/70 bg-surface-raised/20',
      ].join(' ')}
    >
      {/* Eyebrow — instrument-panel readout language, matches Toast */}
      <span
        className={[
          'text-[10px] font-medium tracking-[0.22em] uppercase leading-none',
          'text-txt-muted',
          'shrink-0',
        ].join(' ')}
      >
        Crypto Activity
      </span>

      {/* Primary line — invested AUD as the figure, buy count as the tail */}
      <span className="flex items-baseline gap-2 shrink-0">
        <span
          data-numeric
          className={[
            'font-mono text-[14px] leading-none tracking-tight',
            'text-txt-primary',
          ].join(' ')}
        >
          {AUD.format(activity.total_aud_invested)}
        </span>
        <span className="text-[12px] leading-none tracking-tight text-txt-muted">
          invested
        </span>
        <span
          aria-hidden="true"
          className="text-[11px] leading-none tracking-tight text-txt-muted/70 px-0.5"
        >
          ·
        </span>
        <span
          data-numeric
          className={[
            'font-mono text-[13px] leading-none tracking-tight',
            'text-txt-secondary',
          ].join(' ')}
        >
          {totalBuys.toLocaleString('en-AU')}
        </span>
        <span className="text-[12px] leading-none tracking-tight text-txt-muted">
          {totalBuys === 1 ? 'buy' : 'buys'}
        </span>
      </span>

      {/* Hairline divider — only renders when chips follow, so the row
          collapses gracefully when no per-asset data is present. */}
      {visible.length > 0 && (
        <span className="h-3 w-px bg-surface-border/60" aria-hidden="true" />
      )}

      {/* Per-asset chips — wrap onto a second line on narrow viewports.
          Each chip carries a ticker eyebrow + AUD figure; sized to read
          as a tag rather than a button (no hover affordance — read-only). */}
      <ul
        role="list"
        className="flex flex-wrap items-center gap-1.5 min-w-0"
        aria-label="Per-asset crypto spend"
      >
        {visible.map((entry) => (
          <li
            key={entry.symbol}
            className={[
              'inline-flex items-baseline gap-1.5 px-2 py-1',
              'rounded-[6px] border border-surface-border/50 bg-surface/60',
              // Subtle hover lift — confirms read-only by NOT changing
              // colour or border, just nudging the surface tone.
              'transition-colors duration-150 ease-out',
              'hover:bg-surface-raised/40',
            ].join(' ')}
          >
            <span
              className={[
                'text-[9.5px] font-medium tracking-[0.18em] uppercase leading-none',
                'text-txt-muted',
              ].join(' ')}
            >
              {entry.symbol}
            </span>
            <span
              data-numeric
              className={[
                'font-mono text-[11.5px] leading-none tracking-tight',
                'text-txt-secondary',
              ].join(' ')}
            >
              {AUD.format(entry.audSpent)}
            </span>
          </li>
        ))}
        {overflowCount > 0 && (
          <li
            className={[
              'inline-flex items-center px-2 py-1',
              'rounded-[6px] border border-surface-border/40 bg-transparent',
              'text-[10.5px] tracking-tight text-txt-muted leading-none',
            ].join(' ')}
            aria-label={`${overflowCount} more assets not shown`}
          >
            +{overflowCount} more
          </li>
        )}
      </ul>
    </section>
  )
}
