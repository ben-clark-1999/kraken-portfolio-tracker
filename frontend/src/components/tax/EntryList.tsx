import { useEffect, useMemo, useRef, useState } from 'react'
import type { JSX, MouseEvent as ReactMouseEvent } from 'react'
import { MoreHorizontal, Plus, Search } from 'lucide-react'

import type { TaxEntry, TaxEntryKind } from '../../types/tax'
import { TYPE_LABELS } from '../../types/tax'
import AttachmentChip from './AttachmentChip'

/* ──────────────────────────────────────────────────────────────────────────
 * EntryList — the workhorse list of entries for one kind in one FY.
 *
 * Design rationale: this is where the user actually does the work, so it
 * earns more visual weight than the surrounding summary strips — but only
 * just. Each row is a ledger line, not a card. Hierarchy comes from type
 * weight, monospaced numerics, and tabular alignment, not from boxes.
 *
 *   • Section header: kind label as the dominant heading; entry count and
 *     total AUD live behind a small monospaced eyebrow + numeric pair so
 *     the totals never get mistaken for a kind-of label. "+ Add" is a
 *     restrained ghost button — primary intent without primary colour
 *     weight, since this list will appear three times stacked and three
 *     primary-button cluttered would shout.
 *   • Filter row: a single hairline-bordered surface containing a search
 *     input (with lucide Search prefix) and a type dropdown. Both are
 *     optional UI — the section header is always visible above. Filters
 *     run client-side; a parent debounce isn't needed at our row counts.
 *   • Top 5 entries shown by default; "Show all (N)" reveals the full
 *     list when there's more. The truncation is a comfort affordance
 *     (the FY accordion already collapses the whole section), not a
 *     pagination boundary.
 *   • Each row: date in a small monospaced left column, description as
 *     the primary line, type label as a tiny eyebrow beneath it. On the
 *     right: monospaced AUD amount, attachment count chips (each clickable
 *     to view), and a kebab menu for Edit / Delete. The kebab is a
 *     popover that opens above the row so it doesn't push siblings down.
 *   • Loading state: a stack of skeleton rows mirroring the populated
 *     row geometry, with a quiet pulse on the description and amount
 *     placeholders. Empty state: a single muted line with "+ Add" inline
 *     as a text-link.
 *   • Optimistic delete: parent's useTaxData hook handles the optimistic
 *     update + rollback. We just call onDelete(entry).
 *
 * No left-edge accent stripes (banned). Punctuation lives in eyebrows,
 * the Plus glyph on "+ Add", and the kraken accent that appears on the
 * monospaced count when a filter is active.
 * ────────────────────────────────────────────────────────────────────── */

interface EntryListProps {
  kind: TaxEntryKind
  fy: string
  entries: TaxEntry[] | undefined
  onAdd: () => void
  onEdit: (entry: TaxEntry) => void
  onDelete: (entry: TaxEntry) => void
  onViewAttachment: (attachmentId: string) => void
}

/** Reader-friendly heading per kind. Capitalised correctly for sentence-case
 *  surroundings — no all-caps anywhere except the eyebrow tier. */
const KIND_LABELS: Record<TaxEntryKind, { heading: string; singular: string }> = {
  income: { heading: 'Income', singular: 'income entry' },
  tax_paid: { heading: 'Tax paid', singular: 'tax-paid entry' },
  deductible: { heading: 'Deductibles', singular: 'deductible' },
}

/** AUD formatter — two decimals here (unlike the strip), since these are
 *  the raw transaction amounts. Eye expects cents on a ledger line. */
const AUD = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Date formatter — short, scannable, monospaced. en-AU gives DD/MM/YYYY. */
const DATE_FMT = new Intl.DateTimeFormat('en-AU', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

const VISIBLE_LIMIT = 5

/**
 * Format a stored ISO date (YYYY-MM-DD) to a display label without
 * stumbling over local-timezone offsets. Backend stores civil dates so
 * we mount them at noon to avoid an "off-by-a-day" near tz boundaries.
 */
function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  if (!y || !m || !d) return iso
  const date = new Date(y, m - 1, d, 12)
  return DATE_FMT.format(date)
}

/* ── Component ──────────────────────────────────────────────────────────── */

export default function EntryList({
  kind,
  fy,
  entries,
  onAdd,
  onEdit,
  onDelete,
  onViewAttachment,
}: EntryListProps): JSX.Element {
  const labels = KIND_LABELS[kind]

  /* Filter / search state — both client-side. Empty strings are the no-op
     case so we don't have to special-case them inside the filter pipeline. */
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [search, setSearch] = useState<string>('')
  const [showAll, setShowAll] = useState<boolean>(false)

  /* Derive visible/filtered entries. Memoised because typing into the
     search box re-renders this component on every keystroke; we don't
     want to re-walk the array if neither the entries nor the filter
     changed. */
  const filtered = useMemo<TaxEntry[]>(() => {
    if (!entries) return []
    const q = search.trim().toLowerCase()
    return entries.filter((e) => {
      if (typeFilter && e.type !== typeFilter) return false
      if (q && !e.description.toLowerCase().includes(q)) return false
      return true
    })
  }, [entries, typeFilter, search])

  const total = useMemo<number>(
    () => filtered.reduce((acc, e) => acc + e.amount_aud, 0),
    [filtered],
  )
  const filterActive = typeFilter !== '' || search.trim() !== ''

  /* Available type options come from the entries themselves. We could
     hard-code the kind→types lookup, but driving it from data means the
     dropdown only ever shows types the user actually has — no empty
     "Dividends" filter on a list of pure salary entries. */
  const availableTypes = useMemo<string[]>(() => {
    if (!entries) return []
    const seen = new Set<string>()
    for (const e of entries) seen.add(e.type)
    return [...seen].sort()
  }, [entries])

  const visible = showAll ? filtered : filtered.slice(0, VISIBLE_LIMIT)
  const hiddenCount = filtered.length - visible.length

  /* ── Render branches ────────────────────────────────────────────────── */

  // Loading — entries undefined means "haven't fetched yet"
  if (entries === undefined) {
    return (
      <section
        aria-label={`${labels.heading} — loading`}
        className="flex flex-col gap-3"
      >
        <Header
          heading={labels.heading}
          count={0}
          total={0}
          onAdd={onAdd}
          filterActive={false}
          isLoading
        />
        <SkeletonRows />
      </section>
    )
  }

  // Empty — entries is [] after a successful load
  if (entries.length === 0) {
    return (
      <section
        aria-label={`${labels.heading} — empty`}
        className="flex flex-col gap-3"
      >
        <Header
          heading={labels.heading}
          count={0}
          total={0}
          onAdd={onAdd}
          filterActive={false}
        />
        <EmptyMessage labels={labels} fy={fy} onAdd={onAdd} />
      </section>
    )
  }

  // Populated
  return (
    <section
      aria-label={labels.heading}
      className="flex flex-col gap-3"
    >
      <Header
        heading={labels.heading}
        count={filterActive ? filtered.length : entries.length}
        total={filterActive ? total : entries.reduce((a, e) => a + e.amount_aud, 0)}
        onAdd={onAdd}
        filterActive={filterActive}
      />

      {/* Filter row — show only when there's enough data for filters to
          earn their pixels. A single entry list doesn't need a search. */}
      {entries.length > 1 && (
        <FilterRow
          search={search}
          onSearchChange={setSearch}
          typeFilter={typeFilter}
          onTypeFilterChange={setTypeFilter}
          availableTypes={availableTypes}
        />
      )}

      {/* Filtered-empty (entries exist, but the filter cleared them) */}
      {filtered.length === 0 && (
        <p className="px-4 py-3 text-[12.5px] tracking-tight text-txt-muted">
          No {labels.heading.toLowerCase()} matches the current filter.
        </p>
      )}

      {/* The ledger itself */}
      {filtered.length > 0 && (
        <ul
          role="list"
          className={[
            'flex flex-col rounded-[10px] border border-surface-border/70 overflow-hidden',
            'bg-surface-raised/15',
          ].join(' ')}
        >
          {visible.map((entry) => (
            <EntryRow
              key={entry.id}
              entry={entry}
              onEdit={onEdit}
              onDelete={onDelete}
              onViewAttachment={onViewAttachment}
            />
          ))}
        </ul>
      )}

      {/* Show-all toggle — only when there's something hidden behind the
          fold, AND we're currently showing the truncated view. */}
      {hiddenCount > 0 && !showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className={[
            'self-start text-[12px] tracking-tight font-medium',
            'text-kraken/85 hover:text-kraken',
            'transition-colors duration-150 ease-out',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken rounded-sm',
          ].join(' ')}
        >
          Show all ({filtered.length})
        </button>
      )}
      {showAll && filtered.length > VISIBLE_LIMIT && (
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className={[
            'self-start text-[12px] tracking-tight font-medium',
            'text-txt-muted hover:text-txt-secondary',
            'transition-colors duration-150 ease-out',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken rounded-sm',
          ].join(' ')}
        >
          Show fewer
        </button>
      )}
    </section>
  )
}

/* ── Header ─────────────────────────────────────────────────────────────── */

interface HeaderProps {
  heading: string
  count: number
  total: number
  onAdd: () => void
  filterActive: boolean
  isLoading?: boolean
}

function Header({
  heading,
  count,
  total,
  onAdd,
  filterActive,
  isLoading = false,
}: HeaderProps): JSX.Element {
  return (
    <div className="flex items-end justify-between gap-4 px-1">
      <div className="flex items-baseline gap-3 min-w-0">
        <h4
          className={[
            'text-[14px] font-medium leading-none tracking-tight',
            'text-txt-primary',
          ].join(' ')}
        >
          {heading}
        </h4>

        {!isLoading && (
          <span className="flex items-baseline gap-1.5 shrink-0">
            <span
              data-numeric
              className={[
                'font-mono text-[11px] leading-none tracking-tight',
                filterActive ? 'text-kraken/85' : 'text-txt-muted',
              ].join(' ')}
            >
              {count}
            </span>
            <span className="text-[10px] leading-none tracking-[0.22em] uppercase text-txt-muted/85 font-medium">
              {count === 1 ? 'entry' : 'entries'}
            </span>
            <span
              aria-hidden="true"
              className="text-[11px] leading-none text-txt-muted/60 px-0.5"
            >
              ·
            </span>
            <span
              data-numeric
              className={[
                'font-mono text-[12px] leading-none tracking-tight',
                'text-txt-secondary',
              ].join(' ')}
            >
              {AUD.format(total)}
            </span>
          </span>
        )}
      </div>

      {/* Add button — ghost style; primary intent without competing with
          three siblings on the same page. The kraken tint lives only on
          the Plus glyph until hover. */}
      <button
        type="button"
        onClick={onAdd}
        className={[
          'group inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 shrink-0',
          'border border-surface-border bg-transparent',
          'text-[12px] font-medium tracking-tight text-txt-secondary',
          'transition-[background-color,border-color,color,transform] duration-150 ease-out',
          'hover:bg-surface-raised/40 hover:border-kraken/40 hover:text-txt-primary',
          'active:scale-[0.985]',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
        ].join(' ')}
      >
        <Plus
          aria-hidden="true"
          strokeWidth={2}
          className={[
            'h-3.5 w-3.5 text-kraken/80 group-hover:text-kraken',
            'transition-colors duration-150 ease-out',
          ].join(' ')}
        />
        <span>Add</span>
      </button>
    </div>
  )
}

/* ── Filter row ─────────────────────────────────────────────────────────── */

interface FilterRowProps {
  search: string
  onSearchChange: (s: string) => void
  typeFilter: string
  onTypeFilterChange: (t: string) => void
  availableTypes: string[]
}

function FilterRow({
  search,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  availableTypes,
}: FilterRowProps): JSX.Element {
  return (
    <div
      className={[
        'flex flex-wrap items-center gap-2 px-1',
        // No bordered container — the inputs themselves carry the
        // hairline. Wrapping them in another border would make a row
        // of nested boxes, which we don't do here.
      ].join(' ')}
    >
      {/* Search input — Search glyph as a prefix inside the field, not a
          separate icon-button. Field stretches to consume the row's slack. */}
      <div className="relative flex-1 min-w-[180px]">
        <Search
          aria-hidden="true"
          strokeWidth={1.75}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-txt-muted"
        />
        <input
          type="search"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search descriptions"
          aria-label="Search entries"
          className={[
            'w-full pl-8 pr-3 py-1.5',
            'rounded-md border border-surface-border bg-transparent',
            'text-[12.5px] tracking-tight text-txt-primary placeholder:text-txt-muted',
            'transition-[border-color,background-color] duration-150 ease-out',
            'hover:border-kraken/40',
            'focus:border-kraken/60 focus:bg-surface-raised/30',
            'focus-visible:outline-none',
          ].join(' ')}
        />
      </div>

      {/* Type filter dropdown — only renders when there's more than one
          type in scope; a single-type list doesn't need this control. */}
      {availableTypes.length > 1 && (
        <select
          value={typeFilter}
          onChange={(e) => onTypeFilterChange(e.target.value)}
          aria-label="Filter by type"
          className={[
            'py-1.5 px-2.5 pr-7 rounded-md',
            'border border-surface-border bg-transparent',
            'text-[12px] tracking-tight text-txt-secondary',
            'transition-[border-color,background-color,color] duration-150 ease-out',
            'hover:border-kraken/40 hover:text-txt-primary',
            'focus:border-kraken/60',
            'focus-visible:outline-none',
            // Native chevron is fine — it's quiet enough, and replacing
            // it requires building a popover from scratch (Task 21+ work).
          ].join(' ')}
        >
          <option value="">All types</option>
          {availableTypes.map((t) => (
            <option key={t} value={t}>
              {TYPE_LABELS[t] ?? t}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

/* ── Skeleton rows ──────────────────────────────────────────────────────── */

/**
 * Quiet, atmospheric skeleton — three rows that mirror the populated row's
 * geometry. Pulses use the existing animate-pulse-subtle keyframe with
 * staggered delays so the stack reads as a calibration sweep rather than
 * a generic "loading" shimmer. No spinner.
 */
function SkeletonRows(): JSX.Element {
  return (
    <ul
      role="list"
      aria-hidden="true"
      className={[
        'flex flex-col rounded-[10px] border border-surface-border/70 overflow-hidden',
        'bg-surface-raised/15',
      ].join(' ')}
    >
      {[0, 1, 2].map((i) => (
        <li
          key={i}
          className="flex items-center gap-4 px-4 py-3 border-b border-surface-border/50 last:border-b-0"
        >
          {/* Date column placeholder */}
          <span
            className="h-2.5 w-16 bg-surface-border/60 rounded animate-pulse-subtle"
            style={{ animationDelay: `${i * 180}ms` }}
          />
          {/* Description placeholder */}
          <span className="flex-1 flex flex-col gap-1.5">
            <span
              className="h-2.5 w-2/5 bg-surface-border/70 rounded animate-pulse-subtle"
              style={{ animationDelay: `${i * 180 + 60}ms` }}
            />
            <span
              className="h-2 w-1/4 bg-surface-border/40 rounded animate-pulse-subtle"
              style={{ animationDelay: `${i * 180 + 120}ms` }}
            />
          </span>
          {/* Amount placeholder */}
          <span
            className="h-2.5 w-20 bg-surface-border/60 rounded animate-pulse-subtle"
            style={{ animationDelay: `${i * 180 + 180}ms` }}
          />
        </li>
      ))}
    </ul>
  )
}

/* ── Empty message ──────────────────────────────────────────────────────── */

interface EmptyMessageProps {
  labels: { heading: string }
  fy: string
  onAdd: () => void
}

function EmptyMessage({ labels, fy, onAdd }: EmptyMessageProps): JSX.Element {
  // Format FY identifier with the proper en-dash for typography polish —
  // matches FYSection's formatFYLabel treatment so the eye reads the same
  // range character throughout the page.
  const prettyFY = `FY ${fy.replace('-', '–')}`
  return (
    <p
      className={[
        'px-4 py-3 rounded-[10px] border border-surface-border/60 bg-surface-raised/10',
        'text-[12.5px] tracking-tight text-txt-muted',
      ].join(' ')}
    >
      No {labels.heading.toLowerCase()} for {prettyFY}.{' '}
      <button
        type="button"
        onClick={onAdd}
        className={[
          'text-kraken/85 hover:text-kraken font-medium',
          'transition-colors duration-150 ease-out',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken rounded-sm',
        ].join(' ')}
      >
        + Add one
      </button>
      .
    </p>
  )
}

/* ── Single row ─────────────────────────────────────────────────────────── */

interface EntryRowProps {
  entry: TaxEntry
  onEdit: (entry: TaxEntry) => void
  onDelete: (entry: TaxEntry) => void
  onViewAttachment: (attachmentId: string) => void
}

function EntryRow({
  entry,
  onEdit,
  onDelete,
  onViewAttachment,
}: EntryRowProps): JSX.Element {
  const typeLabel = TYPE_LABELS[entry.type] ?? entry.type

  return (
    <li
      className={[
        'group flex items-center gap-4 px-4 py-3',
        'border-b border-surface-border/50 last:border-b-0',
        'transition-colors duration-150 ease-out',
        'hover:bg-surface-raised/30',
      ].join(' ')}
    >
      {/* Date — left column, monospaced for column alignment across rows.
          Fixed width so the description column starts at the same offset
          on every row regardless of date length. */}
      <span
        data-numeric
        className={[
          'font-mono text-[11.5px] tracking-tight leading-none shrink-0',
          'text-txt-muted',
          'w-[78px]',
        ].join(' ')}
      >
        {formatDate(entry.date)}
      </span>

      {/* Description + type eyebrow stack */}
      <span className="flex-1 min-w-0 flex flex-col gap-1">
        <span
          className={[
            'text-[13.5px] tracking-tight leading-snug truncate',
            'text-txt-primary',
          ].join(' ')}
          title={entry.description}
        >
          {entry.description}
        </span>
        <span
          className={[
            'text-[9.5px] font-medium tracking-[0.22em] uppercase leading-none',
            'text-txt-muted',
          ].join(' ')}
        >
          {typeLabel}
        </span>
      </span>

      {/* Attachment chips — share the AttachmentChip component with the
          drawer so the filename, size, and content-type readout is
          identical across surfaces. EntryList rows don't allow removal
          (the chip is bound to a persisted entry; deleting it requires
          a dedicated server-side flow that's deferred). */}
      {entry.attachments.length > 0 && (
        <span className="flex items-center gap-1.5 shrink-0 max-w-[40%]">
          {entry.attachments.map((att) => (
            <AttachmentChip
              key={att.id}
              attachment={att}
              onView={() => onViewAttachment(att.id)}
            />
          ))}
        </span>
      )}

      {/* Amount — right-aligned, monospaced, slightly heavier weight. The
          numerics column is tabular so vertical scanning aligns cleanly
          across rows of different magnitudes. */}
      <span
        data-numeric
        className={[
          'font-mono text-[13px] tracking-tight leading-none shrink-0',
          'text-txt-primary text-right tabular-nums',
          'min-w-[88px]',
        ].join(' ')}
      >
        {AUD.format(entry.amount_aud)}
      </span>

      {/* Kebab menu — opens an inline popover with Edit/Delete. The popover
          mounts inside the row but positions absolutely so it doesn't push
          siblings down. Opacity-only on the trigger means the menu surface
          itself is always solid. */}
      <RowMenu entry={entry} onEdit={onEdit} onDelete={onDelete} />
    </li>
  )
}

/* ── Row menu (kebab popover) ───────────────────────────────────────────── */

interface RowMenuProps {
  entry: TaxEntry
  onEdit: (entry: TaxEntry) => void
  onDelete: (entry: TaxEntry) => void
}

function RowMenu({ entry, onEdit, onDelete }: RowMenuProps): JSX.Element {
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement | null>(null)

  /* Close on outside click + Escape. Cheap document-level listener; no
     need for a portal because the row is wide enough that the popover
     never overflows the page. */
  useEffect(() => {
    if (!open) return
    function onDocClick(ev: MouseEvent): void {
      if (!wrapperRef.current) return
      if (!wrapperRef.current.contains(ev.target as Node)) setOpen(false)
    }
    function onKey(ev: KeyboardEvent): void {
      if (ev.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function handleEdit(ev: ReactMouseEvent): void {
    ev.stopPropagation()
    setOpen(false)
    onEdit(entry)
  }
  function handleDelete(ev: ReactMouseEvent): void {
    ev.stopPropagation()
    setOpen(false)
    onDelete(entry)
  }

  return (
    <div ref={wrapperRef} className="relative shrink-0">
      <button
        type="button"
        onClick={(ev) => {
          ev.stopPropagation()
          setOpen((o) => !o)
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Actions for ${entry.description}`}
        className={[
          'inline-flex items-center justify-center h-7 w-7 rounded-md',
          'text-txt-muted hover:text-txt-primary hover:bg-surface-raised/60',
          'transition-colors duration-150 ease-out',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
          // Quietly visible by default; the entire row's hover affordance
          // already promotes the icon enough — no opacity hide trick.
        ].join(' ')}
      >
        <MoreHorizontal aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Entry actions"
          className={[
            'absolute right-0 top-[calc(100%+4px)] z-20 min-w-[140px]',
            'rounded-md border border-surface-border bg-surface/95 backdrop-blur-md',
            'shadow-[0_8px_24px_-12px_rgba(0,0,0,0.6),0_2px_6px_-2px_rgba(0,0,0,0.4)]',
            'overflow-hidden',
            // Fade-in — matches the Toast entrance language.
            'animate-fade-in',
          ].join(' ')}
        >
          <button
            type="button"
            role="menuitem"
            onClick={handleEdit}
            className={[
              'block w-full px-3 py-2 text-left',
              'text-[12.5px] tracking-tight text-txt-primary',
              'transition-colors duration-150 ease-out',
              'hover:bg-surface-raised/50',
              'focus-visible:outline-none focus-visible:bg-surface-raised/60',
            ].join(' ')}
          >
            Edit
          </button>
          <div className="h-px bg-surface-border/70" aria-hidden="true" />
          <button
            type="button"
            role="menuitem"
            onClick={handleDelete}
            className={[
              'block w-full px-3 py-2 text-left',
              'text-[12.5px] tracking-tight text-loss',
              'transition-colors duration-150 ease-out',
              'hover:bg-loss/10',
              'focus-visible:outline-none focus-visible:bg-loss/12',
            ].join(' ')}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  )
}
