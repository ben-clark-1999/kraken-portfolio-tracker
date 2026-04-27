import type { JSX } from 'react'
import { ChevronRight } from 'lucide-react'

import type { FYOverview } from '../../types/tax'
import { currentFinancialYear } from '../../utils/financialYear'

/* ──────────────────────────────────────────────────────────────────────────
 * FYSection — single financial-year row in the accordion.
 *
 * Design rationale: each section is a hairline-bordered row in a vertical
 * ledger. Header is a button-like region with the FY label on the left and
 * the Net total on the right; the chevron mediates expansion state. The
 * currently-active FY gets a kraken-tinted year label and a small "CURRENT"
 * eyebrow — restrained punctuation that confirms which row is "now"
 * without ever shouting.
 *
 *   • No left-edge accent stripe (banned). Active state is communicated
 *     via the year-label tint and the eyebrow; the Tab.tsx-style box-
 *     shadow approach is reserved for navigation, not data rows.
 *   • Net = income − deductibles. Tax paid is informational; counting
 *     it here would conflate "I paid tax" with "I lost money," which is
 *     wrong. The semantic is: what did this year clear?
 *   • Expansion uses the grid-rows trick (1fr ↔ 0fr) so we animate
 *     CSS properties that don't trigger layout thrash and don't require
 *     measuring children. Pairs with an opacity fade on the inner panel.
 *   • Chevron rotates 90° rather than swapping icons — a single moving
 *     part reads more refined than icon swaps.
 *   • aria-expanded on the toggle, aria-controls + role="region" on the
 *     body so screen readers can navigate the accordion semantically.
 * ────────────────────────────────────────────────────────────────────── */

interface FYSectionProps {
  fy: string
  overview: FYOverview
  expanded: boolean
  onToggle: () => void
  children: React.ReactNode
}

/**
 * AUD whole-dollar formatter for the header Net readout. Module-scoped so
 * we don't allocate a NumberFormat on every render of every section.
 */
const AUD = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  maximumFractionDigits: 0,
})

/**
 * Format an AU FY identifier ("2025-26") as a typographically polished
 * label ("FY 2025–26"). Replaces the ASCII hyphen with an en-dash so the
 * range reads as a range — this is the small detail that separates a
 * built-on-a-Friday-night dashboard from an instrument.
 */
function formatFYLabel(fy: string): string {
  return `FY ${fy.replace('-', '–')}`
}

export default function FYSection({
  fy,
  overview,
  expanded,
  onToggle,
  children,
}: FYSectionProps): JSX.Element {
  const isCurrent = fy === currentFinancialYear()
  const net = overview.income_total_aud - overview.deductibles_total_aud
  const netNegative = net < 0

  // Generated id pair so aria-controls / aria-labelledby pin the toggle
  // to its body region without colliding across multiple sections.
  const headerId = `fy-${fy}-header`
  const bodyId = `fy-${fy}-body`

  return (
    <section className="border-b border-surface-border/70 last:border-b-0">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <h3 className="m-0">
        <button
          type="button"
          id={headerId}
          onClick={onToggle}
          aria-expanded={expanded}
          aria-controls={bodyId}
          className={[
            // Full-width clickable surface — the entire row is the toggle.
            'group w-full flex items-center gap-4 px-5 py-4 text-left',
            // Subtle hover/active backplate. No accent stripe — the
            // chevron rotation and tint changes carry the affordance.
            'transition-colors duration-150 ease-out',
            'hover:bg-surface-raised/40',
            expanded ? 'bg-surface-raised/25' : '',
            // Focus — handled by the global :focus-visible rule which
            // applies the kraken outline.
            'focus-visible:outline-none focus-visible:bg-surface-raised/40',
          ].join(' ')}
        >
          {/* Chevron — single icon, rotates between collapsed (0deg) and
              expanded (90deg). One moving part. */}
          <ChevronRight
            aria-hidden="true"
            strokeWidth={1.75}
            className={[
              'h-4 w-4 shrink-0',
              'transition-[transform,color] duration-200 ease-out',
              expanded ? 'rotate-90' : '',
              expanded || isCurrent
                ? 'text-kraken'
                : 'text-txt-muted group-hover:text-txt-secondary',
            ].join(' ')}
          />

          {/* FY label column — current FY gets the kraken accent on the
              year and a small "CURRENT" eyebrow chip to its right. */}
          <span className="flex items-baseline gap-3 min-w-0">
            <span
              className={[
                'text-[15px] font-medium tracking-tight leading-none',
                isCurrent ? 'text-kraken' : 'text-txt-primary',
              ].join(' ')}
            >
              {formatFYLabel(fy)}
            </span>
            {isCurrent && (
              <span
                className={[
                  'text-[9.5px] font-medium tracking-[0.24em] uppercase leading-none',
                  'text-kraken/85',
                ].join(' ')}
                aria-label="Current financial year"
              >
                Current
              </span>
            )}
          </span>

          {/* Spacer — pushes the Net readout to the right edge */}
          <span className="flex-1" aria-hidden="true" />

          {/* Net readout — eyebrow above, monospaced amount below.
              Right-aligned so the figures from each row form a clean
              vertical column when scanning the accordion. */}
          <span className="flex flex-col items-end gap-1 shrink-0">
            <span
              className={[
                'text-[9.5px] font-medium tracking-[0.24em] uppercase leading-none',
                'text-txt-muted',
              ].join(' ')}
            >
              Net
            </span>
            <span
              data-numeric
              className={[
                'font-mono text-[14px] leading-none tracking-tight',
                netNegative ? 'text-loss' : 'text-txt-primary',
              ].join(' ')}
            >
              {AUD.format(net)}
            </span>
          </span>
        </button>
      </h3>

      {/* ── Body ───────────────────────────────────────────────────────────
          grid-template-rows: 1fr ↔ 0fr is the modern, layout-safe height
          animation. The inner div has `min-h-0 overflow-hidden` so it
          can collapse fully. Opacity fades alongside so the content
          doesn't peek through during the transition.

          aria-hidden mirrors the visual state so screen readers don't
          read collapsed content. The role="region" + aria-labelledby
          pairing makes each body a navigable landmark linked to its
          header. */}
      <div
        id={bodyId}
        role="region"
        aria-labelledby={headerId}
        aria-hidden={!expanded}
        className={[
          'grid transition-[grid-template-rows,opacity] duration-300 ease-out',
          expanded
            ? 'grid-rows-[1fr] opacity-100'
            : 'grid-rows-[0fr] opacity-0 pointer-events-none',
        ].join(' ')}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="px-5 pb-6 pt-1">{children}</div>
        </div>
      </div>
    </section>
  )
}
