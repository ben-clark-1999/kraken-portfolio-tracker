import { useCallback, useEffect, useState } from 'react'
import type { JSX } from 'react'
import { useTaxData } from '../hooks/useTaxData'
import { currentFinancialYear } from '../utils/financialYear'
import FYAccordion from '../components/tax/FYAccordion'
import KrakenActivityRow from '../components/tax/KrakenActivityRow'
import EntryList from '../components/tax/EntryList'
import EntryDrawer from '../components/tax/EntryDrawer'
import { useToast } from '../components/Toast'
import { fetchAttachmentUrl } from '../api/tax'
import type { FYOverview, TaxEntry, TaxEntryCreate, TaxEntryKind } from '../types/tax'

/* ──────────────────────────────────────────────────────────────────────────
 * TaxHub — page shell, four states.
 *
 * Design rationale: this is the entry-point view for the entire tax surface.
 * The loading and empty states have to feel finished even though the rest of
 * the tab is a stub — they're a first impression that decides whether the
 * user trusts the workspace.
 *
 *   • Loading is presented as a calibration readout: a stack of three short
 *     hairline "channels" with staggered subtle pulses — the visual language
 *     of an instrument booting, not a spinner.
 *   • The empty card uses internal asymmetry rather than the canonical
 *     centered-icon empty-state. A left "ledger" rail with a vertical
 *     eyebrow + ruled guides anchors the type hierarchy on the right;
 *     three labelled tracks below teach what the workspace contains.
 *   • Error mirrors the empty silhouette but loss-tinted, restrained.
 *
 * No left-edge accent stripes anywhere (per .impeccable.md and
 * <absolute_bans>). Punctuation lives in icon-wells, eyebrows, and the
 * single kraken accent on the primary action.
 * ────────────────────────────────────────────────────────────────────── */

export default function TaxHub(): JSX.Element {
  const {
    overview,
    overviewError,
    entriesByFY,
    refreshOverview,
    loadEntries,
    createEntry,
    updateEntry,
    deleteEntry,
  } = useTaxData()
  const { showToast } = useToast()

  // Expansion state for the FY accordion. Lives at the page level so a
  // future "expand all", URL-driven deep-link, or persistent-state
  // hydration can swap in without restructuring children. Default
  // expanded set is the current AU FY — the row a returning user is
  // most likely working in.
  const [expandedFYs, setExpandedFYs] = useState<Set<string>>(
    () => new Set([currentFinancialYear()]),
  )
  const toggleFY = (fy: string): void => {
    setExpandedFYs((prev) => {
      const next = new Set(prev)
      if (next.has(fy)) next.delete(fy)
      else next.add(fy)
      return next
    })
  }

  // EntryDrawer state — owned at the page level because the drawer is
  // shared across every FY in the accordion (and the empty-state CTA).
  // `kind: null` in create mode shows the kind picker; otherwise the form
  // renders directly for that kind.
  const [drawer, setDrawer] = useState<{
    open: boolean
    mode: 'create' | 'edit'
    kind: TaxEntryKind | null
    initialEntry?: TaxEntry
  }>({ open: false, mode: 'create', kind: null })

  const handleAdd = (kind: TaxEntryKind): void =>
    setDrawer({ open: true, mode: 'create', kind })
  const handleEdit = (kind: TaxEntryKind, entry: TaxEntry): void =>
    setDrawer({ open: true, mode: 'edit', kind, initialEntry: entry })
  const handleAddFirst = (): void =>
    setDrawer({ open: true, mode: 'create', kind: null })
  const handleCloseDrawer = (): void =>
    setDrawer((d) => ({ ...d, open: false }))

  // Save router — bridges EntryDrawer's typed onSave contract to the
  // appropriate useTaxData mutation. Errors propagate so the drawer can
  // fire its own loss-toast and keep the form open for correction.
  const handleSave = async (
    kind: TaxEntryKind,
    payload: TaxEntryCreate,
    isEdit: boolean,
    id?: string,
  ): Promise<void> => {
    if (isEdit && id) {
      await updateEntry(kind, id, payload)
    } else {
      await createEntry(kind, payload)
    }
  }

  // Attachment view — fetches a signed URL on demand and opens it in a
  // new tab. Wrapped with useCallback so the prop reference stays
  // stable across renders (the drawer's effects depend on it).
  const handleViewAttachment = useCallback(
    async (attachmentId: string): Promise<void> => {
      try {
        const { url } = await fetchAttachmentUrl(attachmentId)
        // _blank + noopener for the same security posture as any
        // outbound link the dashboard surfaces.
        window.open(url, '_blank', 'noopener,noreferrer')
      } catch (e) {
        showToast({
          variant: 'error',
          message: e instanceof Error ? e.message : String(e),
        })
      }
    },
    [showToast],
  )

  let body: JSX.Element
  if (overviewError) {
    body = <ErrorState message={overviewError} onRetry={() => void refreshOverview()} />
  } else if (overview === null) {
    body = <LoadingState />
  } else if (overview.length === 0) {
    body = <EmptyState onAddFirst={handleAddFirst} />
  } else {
    body = (
      <HasDataState
        overview={overview}
        expandedFYs={expandedFYs}
        toggleFY={toggleFY}
        entriesByFY={entriesByFY}
        loadEntries={loadEntries}
        deleteEntry={deleteEntry}
        onAdd={handleAdd}
        onEdit={handleEdit}
        onViewAttachment={handleViewAttachment}
      />
    )
  }

  return (
    <main className="flex-1 min-w-0">
      <div className="max-w-7xl mx-auto px-6">{body}</div>

      <EntryDrawer
        open={drawer.open}
        mode={drawer.mode}
        kind={drawer.kind}
        initialEntry={drawer.initialEntry}
        onClose={handleCloseDrawer}
        onSave={handleSave}
        onViewAttachment={handleViewAttachment}
      />
    </main>
  )
}

/* ── Loading ────────────────────────────────────────────────────────────── */

/**
 * Calibration-readout aesthetic. Three short horizontal channels stacked
 * vertically, each pulsing at a slightly different phase via the
 * pre-existing `animate-pulse-subtle` keyframes with staggered delays.
 * Eyebrow above, footer label below — small, monospaced, instrument-grade.
 *
 * No spinner, no progress bar, no fake percent counter (a fake counter
 * would lie about progress; we don't have a real one to show).
 */
function LoadingState(): JSX.Element {
  return (
    <div className="min-h-[calc(100vh-3rem)] flex items-center justify-center">
      <div className="flex flex-col items-center gap-7" role="status" aria-live="polite">
        <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-txt-muted">
          Tax Workspace
        </span>

        {/* Channel stack — three thin lines, each independently pulsing.
            Width is fixed (not full-bleed) so the pulse reads as a focused
            calibration readout rather than a page-wide loading bar. */}
        <div className="flex flex-col gap-2.5" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="relative h-px w-[120px] overflow-hidden bg-surface-border/60"
            >
              <div
                className="absolute inset-y-0 left-0 w-full bg-kraken/70 animate-pulse-subtle"
                style={{ animationDelay: `${i * 220}ms` }}
              />
            </div>
          ))}
        </div>

        <span className="text-[11px] tracking-tight text-txt-muted">Reading overview…</span>
      </div>
    </div>
  )
}

/* ── Empty ──────────────────────────────────────────────────────────────── */

interface TrackProps {
  eyebrow: string
  label: string
}

function Track({ eyebrow, label }: TrackProps): JSX.Element {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[9.5px] font-medium tracking-[0.24em] uppercase text-txt-muted">
        {eyebrow}
      </span>
      <span className="text-[13px] tracking-tight text-txt-secondary">{label}</span>
    </div>
  )
}

/**
 * First-run card. Asymmetric: a narrow left "ledger spine" with a vertical
 * eyebrow and three ruled hairline guides, then the heading column on the
 * right. Below the card, a thin row of three "tracks" teaches what the
 * workspace contains without resorting to icon grids.
 *
 * The "Add your first entry" CTA opens the EntryDrawer in create mode
 * with no kind preselected — so the user lands on the kind picker first.
 */
interface EmptyStateProps {
  onAddFirst: () => void
}

function EmptyState({ onAddFirst }: EmptyStateProps): JSX.Element {
  return (
    <div className="min-h-[calc(100vh-3rem)] flex items-center justify-center py-12">
      <div className="w-full max-w-2xl flex flex-col gap-10">
        {/* Top eyebrow — confirms location before the heading does */}
        <div className="flex items-center gap-2.5">
          <span className="h-px w-6 bg-kraken/50" aria-hidden="true" />
          <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-kraken/85">
            Tax Workspace
          </span>
          <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-txt-muted">
            · Not Yet Populated
          </span>
        </div>

        {/* The card */}
        <div className="relative rounded-[12px] border border-surface-border bg-surface/80 overflow-hidden">
          <div className="grid grid-cols-[88px_1fr]">
            {/* Ledger spine — vertical eyebrow + three ruled guides */}
            <div
              className="relative border-r border-surface-border/80 py-9"
              aria-hidden="true"
            >
              {/* Vertical eyebrow, rotated 180° so it reads bottom-up */}
              <div className="absolute inset-y-0 left-0 flex items-center justify-center">
                <span
                  className="text-[9.5px] font-medium tracking-[0.32em] uppercase text-txt-muted whitespace-nowrap"
                  style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
                >
                  Ledger · Ready
                </span>
              </div>
              {/* Three subtle ruled guides on the right edge of the spine —
                  evokes the corner of a bound ledger without ever being
                  literal about it. */}
              <div className="absolute right-0 top-1/2 -translate-y-1/2 flex flex-col gap-1.5 pr-3">
                <span className="block h-px w-3 bg-surface-border" />
                <span className="block h-px w-5 bg-surface-border" />
                <span className="block h-px w-3 bg-surface-border" />
              </div>
            </div>

            {/* Heading column */}
            <div className="px-9 py-10 flex flex-col gap-7">
              <div className="flex flex-col gap-3">
                <h1 className="text-[28px] leading-[1.15] tracking-tight font-semibold text-txt-primary">
                  Your tax workspace
                </h1>
                <p className="text-[14px] leading-relaxed text-txt-secondary max-w-[44ch]">
                  Track income, tax paid, and deductibles in one place. Drop in
                  receipts, screenshots, anything tax-related.
                </p>
              </div>

              <div>
                <button
                  type="button"
                  onClick={onAddFirst}
                  className={[
                    'group inline-flex items-center gap-2 rounded-md px-4 py-2.5',
                    'bg-kraken text-white text-[13px] font-medium tracking-tight',
                    'shadow-[0_1px_0_0_rgba(255,255,255,0.08)_inset,0_8px_22px_-12px_rgba(123,97,255,0.7)]',
                    'transition-[background-color,transform,box-shadow] duration-150 ease-out',
                    'hover:bg-kraken-light active:scale-[0.985]',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
                  ].join(' ')}
                >
                  <span
                    aria-hidden="true"
                    className="text-[14px] leading-none translate-y-px"
                  >
                    +
                  </span>
                  <span>Add your first entry</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Tracks — teach the interface, don't just name it */}
        <div
          className="grid grid-cols-3 gap-x-8 gap-y-4 pt-2"
          aria-label="What this workspace tracks"
        >
          <Track eyebrow="Track 01" label="Income — salary, freelance, interest, dividends" />
          <Track eyebrow="Track 02" label="Tax paid — PAYG withholding, instalments, BAS" />
          <Track eyebrow="Track 03" label="Deductibles — software, hardware, services" />
        </div>
      </div>
    </div>
  )
}

/* ── Has data ───────────────────────────────────────────────────────────── */

interface HasDataStateProps {
  overview: FYOverview[]
  expandedFYs: Set<string>
  toggleFY: (fy: string) => void
  entriesByFY: Record<string, Partial<Record<TaxEntryKind, TaxEntry[]>>>
  loadEntries: (kind: TaxEntryKind, fy: string) => Promise<void>
  deleteEntry: (kind: TaxEntryKind, id: string, fy: string) => Promise<void>
  onAdd: (kind: TaxEntryKind) => void
  onEdit: (kind: TaxEntryKind, entry: TaxEntry) => void
  onViewAttachment: (id: string) => void
}

function HasDataState({
  overview,
  expandedFYs,
  toggleFY,
  entriesByFY,
  loadEntries,
  deleteEntry,
  onAdd,
  onEdit,
  onViewAttachment,
}: HasDataStateProps): JSX.Element {
  // Memoise the per-FY overview lookup so renderFYContent can grab the
  // matching row without rescanning the array on every accordion paint.
  // (overview is short enough that this is a polish move, not a perf
  // bottleneck — but FYContent fires the lookup on every render.)
  const overviewByFY = new Map<string, FYOverview>(
    overview.map((row) => [row.financial_year, row]),
  )

  return (
    <div className="pt-10 pb-16 flex flex-col gap-10">
      <header className="flex flex-col gap-2.5">
        <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-kraken/85">
          Tax Workspace
        </span>
        <h1 className="text-[34px] leading-[1.05] tracking-tight font-semibold text-txt-primary">
          Tax
        </h1>
        <p className="text-[14px] leading-relaxed text-txt-secondary max-w-[68ch]">
          Income, tax paid, deductibles, and crypto activity by financial year.
        </p>
      </header>

      <FYAccordion
        overview={overview}
        expandedFYs={expandedFYs}
        onToggleFY={toggleFY}
        renderFYContent={(fy) => {
          const row = overviewByFY.get(fy)
          if (!row) return null
          return (
            <FYContent
              fy={fy}
              overviewRow={row}
              entriesByFY={entriesByFY}
              loadEntries={loadEntries}
              deleteEntry={deleteEntry}
              onAdd={onAdd}
              onEdit={onEdit}
              onViewAttachment={onViewAttachment}
            />
          )
        }}
      />
    </div>
  )
}

/* ── FYContent ───────────────────────────────────────────────────────────
 * Per-FY body — extracted from the inline renderFYContent callback because
 * we need a hook (useEffect) to fire the three loadEntries() calls on
 * mount. Inline arrow-function children can't host hooks.
 *
 *   • Loads income, tax_paid, deductible entries the first time the
 *     wrapper mounts for a given FY. The accordion mounts/unmounts the
 *     body each time it expands, so this is the natural moment to fetch.
 *   • Renders KrakenActivityRow, then EntryList × 3 in a vertical stack
 *     with generous gap. The kraken row is intentionally first so the
 *     read-only reference data settles into the eye before the editable
 *     ledger lines below it.
 *   • Callbacks: onAdd/onEdit/onViewAttachment are stubbed for Task 21+;
 *     onDelete is already real via the hook (with optimistic update).
 * ──────────────────────────────────────────────────────────────────── */

interface FYContentProps {
  fy: string
  overviewRow: FYOverview
  entriesByFY: Record<string, Partial<Record<TaxEntryKind, TaxEntry[]>>>
  loadEntries: (kind: TaxEntryKind, fy: string) => Promise<void>
  deleteEntry: (kind: TaxEntryKind, id: string, fy: string) => Promise<void>
  onAdd: (kind: TaxEntryKind) => void
  onEdit: (kind: TaxEntryKind, entry: TaxEntry) => void
  onViewAttachment: (id: string) => void
}

function FYContent({
  fy,
  overviewRow,
  entriesByFY,
  loadEntries,
  deleteEntry,
  onAdd,
  onEdit,
  onViewAttachment,
}: FYContentProps): JSX.Element {
  // Fire the three loads on mount. We don't await them; the EntryList
  // already renders its loading skeleton against `entries === undefined`.
  // Errors are swallowed at this layer for now — Task 22+ wires toasts.
  useEffect(() => {
    void loadEntries('income', fy).catch((err) => {
      console.error('TaxHub: load income failed', err)
    })
    void loadEntries('tax_paid', fy).catch((err) => {
      console.error('TaxHub: load tax_paid failed', err)
    })
    void loadEntries('deductible', fy).catch((err) => {
      console.error('TaxHub: load deductible failed', err)
    })
  }, [fy, loadEntries])

  const bucket = entriesByFY[fy]

  // onDelete stays local (it's the only path that needs `fy` to scope
  // the optimistic-update bucket). onAdd/onEdit/onViewAttachment all
  // forward up to TaxHub which owns the drawer + signed-URL flow.
  function onDelete(kind: TaxEntryKind, entry: TaxEntry): void {
    deleteEntry(kind, entry.id, fy).catch((err) => {
      console.error('TaxHub: delete failed', err)
    })
  }

  return (
    <div className="flex flex-col gap-7">
      <KrakenActivityRow activity={overviewRow.kraken_activity} />

      <EntryList
        kind="income"
        fy={fy}
        entries={bucket?.income}
        onAdd={() => onAdd('income')}
        onEdit={(entry) => onEdit('income', entry)}
        onDelete={(entry) => onDelete('income', entry)}
        onViewAttachment={onViewAttachment}
      />

      <EntryList
        kind="tax_paid"
        fy={fy}
        entries={bucket?.tax_paid}
        onAdd={() => onAdd('tax_paid')}
        onEdit={(entry) => onEdit('tax_paid', entry)}
        onDelete={(entry) => onDelete('tax_paid', entry)}
        onViewAttachment={onViewAttachment}
      />

      <EntryList
        kind="deductible"
        fy={fy}
        entries={bucket?.deductible}
        onAdd={() => onAdd('deductible')}
        onEdit={(entry) => onEdit('deductible', entry)}
        onDelete={(entry) => onDelete('deductible', entry)}
        onViewAttachment={onViewAttachment}
      />
    </div>
  )
}

/* ── Error ──────────────────────────────────────────────────────────────── */

interface ErrorStateProps {
  message: string
  onRetry: () => void
}

/**
 * Mirrors the empty card silhouette but with a loss-tinted spine. Eyebrow
 * is the failure label (instrument-readout language continued from Toast).
 * "Retry" is a text-button matching the Dashboard's restrained pattern.
 */
function ErrorState({ message, onRetry }: ErrorStateProps): JSX.Element {
  return (
    <div className="min-h-[calc(100vh-3rem)] flex items-center justify-center py-12">
      <div className="w-full max-w-2xl flex flex-col gap-8">
        <div className="flex items-center gap-2.5">
          <span className="h-px w-6 bg-loss/60" aria-hidden="true" />
          <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-loss/85">
            Overview Unreachable
          </span>
        </div>

        <div className="rounded-[12px] border border-surface-border bg-surface/80 overflow-hidden">
          <div className="grid grid-cols-[88px_1fr]">
            <div
              className="relative border-r border-surface-border/80 py-9"
              aria-hidden="true"
            >
              <div className="absolute inset-y-0 left-0 flex items-center justify-center">
                <span
                  className="text-[9.5px] font-medium tracking-[0.32em] uppercase text-loss/70 whitespace-nowrap"
                  style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
                >
                  Status · Failed
                </span>
              </div>
              <div className="absolute right-0 top-1/2 -translate-y-1/2 flex flex-col gap-1.5 pr-3">
                <span className="block h-px w-3 bg-loss/30" />
                <span className="block h-px w-5 bg-loss/30" />
                <span className="block h-px w-3 bg-loss/30" />
              </div>
            </div>

            <div className="px-9 py-10 flex flex-col gap-6" role="alert" aria-live="polite">
              <div className="flex flex-col gap-3">
                <h2 className="text-[22px] leading-[1.2] tracking-tight font-semibold text-txt-primary">
                  Couldn't load your tax overview
                </h2>
                <p className="text-[13px] leading-relaxed text-loss/90 font-mono break-words">
                  {message}
                </p>
              </div>

              <div>
                <button
                  type="button"
                  onClick={onRetry}
                  className={[
                    'inline-flex items-center gap-2 rounded-md px-3.5 py-2',
                    'border border-surface-border bg-surface-raised/50',
                    'text-[12.5px] font-medium tracking-tight text-txt-primary',
                    'transition-[background-color,border-color,transform] duration-150 ease-out',
                    'hover:bg-surface-raised hover:border-kraken/40',
                    'active:scale-[0.985]',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
                  ].join(' ')}
                >
                  Retry
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
