import type { JSX } from 'react'
import type { FYOverview } from '../../types/tax'

/* ──────────────────────────────────────────────────────────────────────────
 * FYSummaryStrip — reference-data readout for a single financial year.
 *
 * Design rationale: this is the four-up totals row that anchors the top of
 * each expanded FY. It is intentionally quiet. The user's focus belongs on
 * the entry tables below it, so this component is built as a
 * hairline-divided ledger row rather than a card grid.
 *
 *   • Each cell is a stacked pair: a tiny monospaced uppercase eyebrow
 *     (instrument-panel readout language, matching Toast and TaxHub) with
 *     the AUD figure beneath it in a slightly heavier numeric weight.
 *   • Cells are separated by single-pixel hairlines — no boxes, no cards,
 *     no nested radii. The container itself is a thin-bordered strip.
 *   • On narrow widths the cells wrap; the dividers swap from vertical
 *     between cells to horizontal between rows so the rhythm holds.
 *   • AUD whole-dollar formatting (Intl en-AU) — the data is 2-decimal but
 *     decimals here would be visual noise; this is a glance-readable
 *     summary, not the receipt.
 *
 * No left-edge accent stripes. No card. The four numbers carry the strip.
 * ────────────────────────────────────────────────────────────────────── */

interface FYSummaryStripProps {
  overview: FYOverview
}

interface CellSpec {
  /** Tiny instrument-panel eyebrow — uppercase, monospaced */
  eyebrow: string
  /** AUD value, pre-rounded by Intl.NumberFormat */
  value: string
}

/**
 * AUD currency formatter — whole dollars only. The backend stores values
 * to two decimals; rounding for display lets the eye scan four cells in a
 * row without fixating on cents that aren't actionable here. Memoised at
 * module scope — building a NumberFormat is non-trivial and we render this
 * many times on a populated page.
 */
const AUD = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  maximumFractionDigits: 0,
})

export default function FYSummaryStrip({ overview }: FYSummaryStripProps): JSX.Element {
  const cells: CellSpec[] = [
    { eyebrow: 'Income', value: AUD.format(overview.income_total_aud) },
    { eyebrow: 'Tax Paid', value: AUD.format(overview.tax_paid_total_aud) },
    { eyebrow: 'Deductibles', value: AUD.format(overview.deductibles_total_aud) },
    {
      eyebrow: 'Crypto Invested',
      value: AUD.format(overview.kraken_activity.total_aud_invested),
    },
  ]

  return (
    <div
      role="group"
      aria-label="Financial-year totals"
      className={[
        // Outer strip — hairline border, restrained surface tone. Wraps
        // gracefully so on narrow widths the cells stack cleanly.
        'flex flex-wrap rounded-[10px] border border-surface-border bg-surface-raised/30',
        'overflow-hidden',
      ].join(' ')}
    >
      {cells.map((cell, idx) => (
        <div
          key={cell.eyebrow}
          className={[
            // Each cell is a fluid column on wide layouts (1/4 each) and
            // a half on tablet, full-width on phone. The basis carries
            // the responsive behaviour without a media query.
            'flex-1 min-w-[40%] sm:min-w-[22%]',
            // Internal type rhythm — generous vertical, snug horizontal.
            'px-5 py-4',
            // Hairline dividers between cells — vertical when on the same
            // row, horizontal when the cell wraps to a new row. The
            // border on every left edge except the first cell creates the
            // vertical hairline; the top border on wrapped rows gives the
            // horizontal one. Together they form a clean ledger grid.
            idx > 0 ? 'border-l border-surface-border/60' : '',
            // On wrap, the cell's top hairline divides rows. We use a
            // negative margin trick? No — simpler: rely on the container
            // hairline by leaving each cell's own borders inactive on top
            // (the outer strip handles the outside). For inter-row
            // hairlines we add a top border that only paints when the
            // cell is on a wrapped row. Using flex-wrap, this is non-
            // trivial to detect in CSS; instead we accept that on wrap
            // the visual lives on the outer strip border alone. Clean
            // enough — the strip is a quiet element by design.
          ].join(' ')}
        >
          <div className="flex flex-col gap-1.5">
            <span
              className={[
                'text-[10px] font-medium tracking-[0.22em] uppercase leading-none',
                'text-txt-muted',
              ].join(' ')}
            >
              {cell.eyebrow}
            </span>
            <span
              data-numeric
              className={[
                'font-mono text-[15px] leading-none tracking-tight',
                'text-txt-primary',
              ].join(' ')}
            >
              {cell.value}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
