import type { JSX } from 'react'

import type { FYOverview } from '../../types/tax'
import FYSection from './FYSection'
import FYSummaryStrip from './FYSummaryStrip'

/* ──────────────────────────────────────────────────────────────────────────
 * FYAccordion — the spine of the Tax tab.
 *
 * Pure presentation: it iterates the FY overview (already sorted descending
 * by the backend) and emits one <FYSection> per row. Expansion state is
 * owned by the parent (TaxHub) so a future "expand all / collapse all" or
 * URL-driven deep link doesn't fight a child for ownership.
 *
 *   • Each section's body renders FYSummaryStrip at the top — the four-up
 *     totals — and below it, whatever the parent supplies via
 *     renderFYContent. In Task 20 that body grows the per-FY entry lists;
 *     today it's a stub. The strip lives here (not in the parent's
 *     renderFYContent) so future entry lists never need to reach into a
 *     totals row that already exists at the section level.
 *   • The outer wrapper is a hairline-bordered scroll-friendly card with
 *     overflow-hidden so the inter-section borders compose into a single
 *     ledger surface.
 * ────────────────────────────────────────────────────────────────────── */

interface FYAccordionProps {
  overview: FYOverview[]
  expandedFYs: Set<string>
  onToggleFY: (fy: string) => void
  renderFYContent: (fy: string) => React.ReactNode
}

export default function FYAccordion({
  overview,
  expandedFYs,
  onToggleFY,
  renderFYContent,
}: FYAccordionProps): JSX.Element {
  return (
    <div
      className={[
        // Single hairline-bounded surface — the inter-section borders
        // (set on each FYSection) divide it into rows. overflow-hidden
        // clips the rounded corners against the children.
        'rounded-[12px] border border-surface-border bg-surface/80 overflow-hidden',
      ].join(' ')}
    >
      {overview.map((row) => {
        const fy = row.financial_year
        const isExpanded = expandedFYs.has(fy)
        return (
          <FYSection
            key={fy}
            fy={fy}
            overview={row}
            expanded={isExpanded}
            onToggle={() => onToggleFY(fy)}
          >
            <div className="flex flex-col gap-5">
              <FYSummaryStrip overview={row} />
              {renderFYContent(fy)}
            </div>
          </FYSection>
        )
      })}
    </div>
  )
}
