import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, JSX } from 'react'
import {
  Loader2,
  Receipt,
  Tag,
  TrendingUp,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { useToast } from '../Toast'
import { deleteAttachment } from '../../api/tax'
import {
  DEDUCTIBLE_TYPES,
  INCOME_TYPES,
  TAX_PAID_TYPES,
  TYPE_LABELS,
} from '../../types/tax'
import type {
  TaxAttachment,
  TaxEntry,
  TaxEntryCreate,
  TaxEntryKind,
} from '../../types/tax'
import FileDropZone from './FileDropZone'
import AttachmentChip from './AttachmentChip'

/* ──────────────────────────────────────────────────────────────────────────
 * EntryDrawer — the create/edit instrument for the Tax Hub.
 *
 * Aesthetic posture: a calm right-side panel that mirrors the instrument-
 * grade feel of TaxHub's empty state and the EntryList ledger lines. It
 * shares the right-edge slot with AgentPanel, so the two are mutually
 * exclusive — opening one should never visually compete with the other
 * (TaxHub never renders AgentPanel anyway, but the geometry is identical
 * so muscle memory is preserved across views).
 *
 *   • Kind picker (create + kind=null): three numbered "channel" cards in a
 *     vertical stack. Numbered eyebrows ("01 / 02 / 03") hint at a mixing-
 *     desk vocabulary without mimicking one literally. Each card has a
 *     tinted icon-well + label + one-line description; hovering the card
 *     promotes the icon-well's tint and lifts the title weight. Click =
 *     commit, the form replaces the picker.
 *   • Header: breadcrumb-style trail ("Tax · Add · Income") that reads as
 *     navigation depth, not ornament. The close button (lucide X) anchors
 *     the right edge — a single restrained affordance that pairs with the
 *     Escape-key close handler.
 *   • Form: stacked field rows, each with a small eyebrow above the input
 *     and an optional helper or error line below. Inputs are hairline-
 *     bordered transparent surfaces — no filled wells, no nested cards.
 *     Numerics (amount) get tabular-nums + monospaced font for the same
 *     ledger-line consistency as EntryList rows.
 *   • Inline validation: eyebrow-style error label ("ERROR · description")
 *     in loss-red, matching Toast's eyebrow language. NEVER an alert().
 *   • Attachment stub: a hairline pill with a dimmed paperclip and an
 *     instrument-grade eyebrow ("Files · Available next release"). Honest
 *     about the gap rather than apologetic.
 *   • Footer: sticky to the drawer's bottom with a hairline top border.
 *     Cancel as a ghost button on the left, Save as a kraken-filled
 *     primary on the right. Saving collapses Save into a pulsing
 *     calibration line (matches the loading-state vocabulary).
 *   • Backdrop: a full-screen tinted layer at the same z-50 stacking
 *     context, captures clicks (closes the drawer) without ever feeling
 *     like a heavy black overlay.
 *   • Motion: 250ms ease-out enter / 200ms ease-in exit on translate +
 *     opacity for both drawer and backdrop. CSS transitions only — no
 *     animation library, no spring physics. Honour reduced-motion.
 *
 * Per .impeccable.md: no left-edge accent stripes, no gradient text, no
 * glassmorphism beyond the existing backdrop-blur on the surface. Every
 * pixel is a tool that earns its place.
 * ────────────────────────────────────────────────────────────────────── */

export type DrawerMode = 'create' | 'edit'

export interface EntryDrawerProps {
  open: boolean
  mode: DrawerMode
  /** null in create mode shows the kind picker; non-null skips it. */
  kind: TaxEntryKind | null
  /** Present iff mode === 'edit'. */
  initialEntry?: TaxEntry
  onClose: () => void
  onSave: (
    kind: TaxEntryKind,
    payload: TaxEntryCreate,
    isEdit: boolean,
    id?: string,
  ) => Promise<void>
  /** Opens an attachment in a new tab (parent owns signed-URL fetch). */
  onViewAttachment?: (id: string) => void
}

/* ── Per-kind config ──────────────────────────────────────────────────────
 * Centralised so the kind picker, the form title, and the type-dropdown
 * options all read from the same source. The "channel" numbering matches
 * the empty-state's "Track 01 / 02 / 03" wording so the user's mental
 * model stays consistent across surfaces.
 * ────────────────────────────────────────────────────────────────────── */

interface KindConfig {
  channel: string
  Icon: LucideIcon
  noun: string // "deductible", "income entry", "tax-paid entry"
  picker: { label: string; description: string }
  types: ReadonlyArray<string>
  defaultType: string
}

const KIND_CONFIG: Record<TaxEntryKind, KindConfig> = {
  income: {
    channel: '01',
    Icon: TrendingUp,
    noun: 'income',
    picker: {
      label: 'Income',
      description: 'Salary, freelance, interest, dividends.',
    },
    types: INCOME_TYPES,
    defaultType: 'salary_wages',
  },
  tax_paid: {
    channel: '02',
    Icon: Receipt,
    noun: 'tax paid',
    picker: {
      label: 'Tax paid',
      description: 'PAYG withholding, instalments, BAS payments.',
    },
    types: TAX_PAID_TYPES,
    defaultType: 'payg_withholding',
  },
  deductible: {
    channel: '03',
    Icon: Tag,
    noun: 'deductible',
    picker: {
      label: 'Deductible',
      description: 'Software, hardware, services, professional development.',
    },
    types: DEDUCTIBLE_TYPES,
    defaultType: 'software',
  },
}

const KIND_ORDER: ReadonlyArray<TaxEntryKind> = ['income', 'tax_paid', 'deductible']

/** Local YYYY-MM-DD for "today" — avoids the toISOString() UTC drift bug
 *  near midnight where a user in a positive offset would see tomorrow's
 *  date as the default. */
function todayISO(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/* ── Form state model ───────────────────────────────────────────────────── */

interface FormValues {
  description: string
  /** Stored as a string so the input can be empty; coerced on submit. */
  amount: string
  date: string
  type: string
  notes: string
}

interface FormErrors {
  description?: string
  amount?: string
  date?: string
  type?: string
  notes?: string
}

const DESC_MAX = 200
const NOTES_MAX = 4000

function emptyValues(kind: TaxEntryKind | null): FormValues {
  return {
    description: '',
    amount: '',
    date: todayISO(),
    type: kind ? KIND_CONFIG[kind].defaultType : '',
    notes: '',
  }
}

function valuesFromEntry(entry: TaxEntry): FormValues {
  return {
    description: entry.description,
    amount: entry.amount_aud.toFixed(2),
    date: entry.date,
    type: entry.type,
    notes: entry.notes ?? '',
  }
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {}

  const description = values.description.trim()
  if (!description) errors.description = 'Add a short description.'
  else if (description.length > DESC_MAX)
    errors.description = `Keep it under ${DESC_MAX} characters.`

  const amount = Number(values.amount)
  if (!values.amount.trim()) errors.amount = 'Enter an amount in AUD.'
  else if (!Number.isFinite(amount)) errors.amount = 'Amount must be a number.'
  else if (amount <= 0) errors.amount = 'Amount must be greater than zero.'

  if (!values.date) errors.date = 'Pick a date.'
  else if (!/^\d{4}-\d{2}-\d{2}$/.test(values.date))
    errors.date = 'Date must be YYYY-MM-DD.'

  if (!values.type) errors.type = 'Choose a type.'

  if (values.notes.length > NOTES_MAX)
    errors.notes = `Keep notes under ${NOTES_MAX} characters.`

  return errors
}

/* ── Component ──────────────────────────────────────────────────────────── */

export default function EntryDrawer({
  open,
  mode,
  kind,
  initialEntry,
  onClose,
  onSave,
  onViewAttachment,
}: EntryDrawerProps): JSX.Element | null {
  const { showToast } = useToast()

  /* "Working kind" — for create mode, this starts as the prop value (which
     may be null) and the picker mutates it. For edit mode, it tracks the
     prop directly. We resolve it below into kindForForm. */
  const [pickedKind, setPickedKind] = useState<TaxEntryKind | null>(kind)

  // Reset picked kind whenever the drawer opens with a new context. We
  // compare against `open` so re-renders without a state shift don't
  // clobber a pick the user just made.
  const lastOpenRef = useRef(false)
  useEffect(() => {
    if (open && !lastOpenRef.current) {
      setPickedKind(kind)
    }
    lastOpenRef.current = open
  }, [open, kind])

  // Edit mode requires a kind (we trust the parent to provide it). In create
  // mode, it comes from pickedKind (which may be null while the picker shows).
  const effectiveKind: TaxEntryKind | null =
    mode === 'edit' ? kind : pickedKind

  /* Form values — driven by the active kind + initialEntry (edit mode). */
  const [values, setValues] = useState<FormValues>(() =>
    mode === 'edit' && initialEntry
      ? valuesFromEntry(initialEntry)
      : emptyValues(effectiveKind),
  )
  const [touched, setTouched] = useState<Record<keyof FormValues, boolean>>({
    description: false,
    amount: false,
    date: false,
    type: false,
    notes: false,
  })
  const [submitAttempted, setSubmitAttempted] = useState(false)
  const [saving, setSaving] = useState(false)

  /* Attachments — collected as the user uploads via FileDropZone. In edit
     mode we hydrate from the entry's existing attachments so they appear
     as chips beneath the dropzone; in create mode we start empty. The
     "initial set" (anything bound to a saved entry) is captured below
     for the close-with-pending-uploads confirm dialog. */
  const [attachments, setAttachments] = useState<TaxAttachment[]>(
    () => initialEntry?.attachments ?? [],
  )
  const initialAttachmentIdsRef = useRef<Set<string>>(
    new Set(initialEntry?.attachments?.map((a) => a.id) ?? []),
  )

  /* Reset / hydrate the form whenever the drawer opens or the active kind
     changes. This is the single point where form state is synchronised
     with props — keeps the rest of the component's state-flow simple. */
  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && initialEntry) {
      setValues(valuesFromEntry(initialEntry))
    } else if (effectiveKind) {
      setValues(emptyValues(effectiveKind))
    } else {
      setValues(emptyValues(null))
    }
    setTouched({
      description: false,
      amount: false,
      date: false,
      type: false,
      notes: false,
    })
    setSubmitAttempted(false)
    setSaving(false)
    // Reset attachment state on every open / context change. Edit mode
    // hydrates from the entry; create mode starts empty.
    const hydrated = mode === 'edit' && initialEntry ? initialEntry.attachments : []
    setAttachments(hydrated)
    initialAttachmentIdsRef.current = new Set(hydrated.map((a) => a.id))
  }, [open, mode, initialEntry, effectiveKind])

  /* Pending-uploads-aware close. Confirms a discard if the user has new
     uploads that would be orphaned. New = present in `attachments` but
     NOT in `initialAttachmentIdsRef` (which captures whatever was bound
     to the saved entry on open). On confirm we delete the orphans
     server-side so the user's storage stays clean. */
  function attemptClose(): void {
    if (saving) return
    const pending = attachments.filter(
      (a) => !initialAttachmentIdsRef.current.has(a.id),
    )
    if (pending.length === 0) {
      onClose()
      return
    }
    const noun = pending.length === 1 ? 'file' : 'files'
    const ok = window.confirm(
      `Discard ${pending.length} uploaded ${noun}? They'll be removed from storage.`,
    )
    if (!ok) return
    // Fire-and-forget delete. Errors are surfaced as toasts but never
    // block the close — the user has decided to abandon them.
    void Promise.allSettled(pending.map((a) => deleteAttachment(a.id))).then(
      (results) => {
        const failed = results.filter((r) => r.status === 'rejected')
        if (failed.length > 0) {
          showToast({
            variant: 'error',
            message: `${failed.length} of ${pending.length} ${noun} couldn't be deleted from storage.`,
          })
        }
      },
    )
    onClose()
  }

  /* Escape closes the drawer (unless mid-save — let the save resolve so
     toast positioning matches the user's expectation). */
  useEffect(() => {
    if (!open) return
    function onKey(ev: KeyboardEvent): void {
      if (ev.key === 'Escape' && !saving) {
        ev.stopPropagation()
        attemptClose()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, saving, attachments])

  /* Body-scroll lock while the drawer is open. The dashboard underneath
     can be tall, and the drawer itself scrolls — locking the body keeps
     the overlay feeling like a focused workspace, not a hovering layer. */
  useEffect(() => {
    if (!open) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [open])

  /* Three-phase mount/visibility lifecycle so we can drive enter + exit
     transitions purely with CSS. 'enter' is the first paint with hidden
     transforms; 'open' is the post-RAF state with translate(0); 'exit' is
     the closing state. We unmount only after the exit duration to keep
     animations honest. */
  const [phase, setPhase] = useState<'enter' | 'open' | 'exit' | 'closed'>('closed')
  useEffect(() => {
    if (open) {
      setPhase('enter')
      const raf = requestAnimationFrame(() => setPhase('open'))
      return () => cancelAnimationFrame(raf)
    }
    if (phase === 'closed') return
    setPhase('exit')
    const t = window.setTimeout(() => setPhase('closed'), 220)
    return () => window.clearTimeout(t)
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open && phase === 'closed') return null

  /* ── Derived display values ──────────────────────────────────────────── */

  const errors = validate(values)
  const showError = (field: keyof FormValues): string | undefined =>
    submitAttempted || touched[field] ? errors[field] : undefined

  const isEdit = mode === 'edit'
  const headerKindLabel = effectiveKind
    ? KIND_CONFIG[effectiveKind].picker.label
    : null
  const headerActionLabel = isEdit ? 'Edit' : 'Add'

  /* ── Handlers ────────────────────────────────────────────────────────── */

  function bind<K extends keyof FormValues>(field: K) {
    return {
      value: values[field],
      onChange: (
        ev: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
      ) => {
        setValues((v) => ({ ...v, [field]: ev.target.value }))
      },
      onBlur: () => setTouched((t) => ({ ...t, [field]: true })),
    }
  }

  async function handleSubmit(ev: FormEvent<HTMLFormElement>): Promise<void> {
    ev.preventDefault()
    if (saving) return
    setSubmitAttempted(true)
    if (!effectiveKind) return
    const v = validate(values)
    if (Object.keys(v).length > 0) {
      // Surface every error at once so the user can fix them in one pass.
      setTouched({
        description: true,
        amount: true,
        date: true,
        type: true,
        notes: true,
      })
      return
    }

    const payload: TaxEntryCreate = {
      description: values.description.trim(),
      amount_aud: Number(values.amount),
      date: values.date,
      type: values.type,
      notes: values.notes.trim() ? values.notes.trim() : null,
      // Only include attachment_ids on create — edit mode keeps the
      // existing bindings server-side (Task 22's add/remove flow for
      // edit is deferred). On create we forward every uploaded id so
      // tax_service rebinds them from PENDING to the new entry.
      ...(isEdit
        ? {}
        : {
            attachment_ids: attachments.map((a) => a.id),
          }),
    }

    setSaving(true)
    try {
      await onSave(effectiveKind, payload, isEdit, initialEntry?.id)
      showToast({
        variant: 'success',
        message: isEdit
          ? `Updated ${KIND_CONFIG[effectiveKind].noun} entry.`
          : `Saved ${KIND_CONFIG[effectiveKind].noun} entry.`,
      })
      onClose()
    } catch (err) {
      showToast({
        variant: 'error',
        message:
          err instanceof Error
            ? err.message
            : `Couldn't save ${KIND_CONFIG[effectiveKind].noun}.`,
      })
      setSaving(false)
    }
  }

  function handleBackdropClick(): void {
    if (saving) return
    attemptClose()
  }

  /* ── Render branches ─────────────────────────────────────────────────── */

  // Show kind picker iff create mode AND no kind has been chosen yet.
  const showPicker = !isEdit && !effectiveKind

  return (
    <>
      {/* Backdrop — quiet tinted scrim. Captures clicks via its own
          handler; never receives the drawer's events because the drawer
          stops propagation at its boundary. */}
      <div
        aria-hidden="true"
        onClick={handleBackdropClick}
        data-phase={phase}
        className={[
          'fixed inset-0 z-40',
          'bg-black/45 backdrop-blur-[1px]',
          'transition-opacity duration-200 ease-out',
          'data-[phase=enter]:opacity-0',
          'data-[phase=open]:opacity-100',
          'data-[phase=exit]:opacity-0',
        ].join(' ')}
      />

      {/* Drawer — the focused work surface. */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={
          showPicker
            ? 'Add tax entry'
            : `${headerActionLabel} ${headerKindLabel ?? 'tax entry'}`
        }
        data-phase={phase}
        className={[
          'fixed inset-y-0 right-0 z-50 w-[480px] max-w-full',
          'flex flex-col bg-surface border-l border-surface-border',
          'shadow-[0_30px_80px_-20px_rgba(0,0,0,0.7)]',
          // Motion — 250ms ease-out enter, 200ms ease-in exit, opacity +
          // translate. Reduced-motion is honoured globally in globals.css.
          'transition-[transform,opacity] duration-[250ms] ease-out will-change-transform',
          'data-[phase=enter]:translate-x-6 data-[phase=enter]:opacity-0',
          'data-[phase=open]:translate-x-0 data-[phase=open]:opacity-100',
          'data-[phase=exit]:translate-x-4 data-[phase=exit]:opacity-0',
          'data-[phase=exit]:duration-200 data-[phase=exit]:ease-in',
        ].join(' ')}
      >
        <DrawerHeader
          mode={mode}
          actionLabel={headerActionLabel}
          kindLabel={headerKindLabel}
          onClose={attemptClose}
          disabled={saving}
        />

        {/* Body — scrollable column. The picker and the form share this
            slot; we cross-fade by re-mounting the appropriate subtree. */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {showPicker ? (
            <KindPicker onPick={(k) => setPickedKind(k)} />
          ) : effectiveKind ? (
            <EntryForm
              kind={effectiveKind}
              values={values}
              bind={bind}
              showError={showError}
              isEdit={isEdit}
              saving={saving}
              onSubmit={handleSubmit}
              onCancel={attemptClose}
              attachments={attachments}
              onAttachmentUploaded={(a) =>
                setAttachments((prev) =>
                  prev.some((x) => x.id === a.id) ? prev : [...prev, a]
                )
              }
              onAttachmentRemove={(id) => {
                // Optimistic local removal. If the chip is a freshly-
                // uploaded one (not in the initial set), also DELETE
                // the row server-side so we don't leak storage.
                setAttachments((prev) => prev.filter((x) => x.id !== id))
                if (!initialAttachmentIdsRef.current.has(id)) {
                  void deleteAttachment(id).catch((err) => {
                    showToast({
                      variant: 'error',
                      message:
                        err instanceof Error
                          ? err.message
                          : "Couldn't remove the file from storage.",
                    })
                  })
                }
              }}
              onAttachmentError={(message) =>
                showToast({ variant: 'error', message })
              }
              onAttachmentView={onViewAttachment}
            />
          ) : null}
        </div>
      </aside>
    </>
  )
}

/* ── Header ──────────────────────────────────────────────────────────────
 * Breadcrumb-style trail on the left ("Tax · Add · Income"), close glyph
 * on the right. Hairline bottom border ties it visually to the rest of
 * the surface. The breadcrumb's last segment fades-in/out as the kind
 * crystallises so the picker→form transition feels stitched together.
 * ──────────────────────────────────────────────────────────────────── */

interface DrawerHeaderProps {
  mode: DrawerMode
  actionLabel: string
  kindLabel: string | null
  onClose: () => void
  disabled: boolean
}

function DrawerHeader({
  actionLabel,
  kindLabel,
  onClose,
  disabled,
}: DrawerHeaderProps): JSX.Element {
  return (
    <header
      className={[
        'flex items-center justify-between gap-4 px-6 py-5',
        'border-b border-surface-border',
      ].join(' ')}
    >
      <nav
        aria-label="Drawer location"
        className="flex items-center gap-2 min-w-0"
      >
        <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-kraken/85 leading-none">
          Tax
        </span>
        <span
          aria-hidden="true"
          className="text-[10px] leading-none text-txt-muted/55"
        >
          ·
        </span>
        <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-txt-muted leading-none">
          {actionLabel}
        </span>
        {kindLabel && (
          <>
            <span
              aria-hidden="true"
              className="text-[10px] leading-none text-txt-muted/55"
            >
              ·
            </span>
            <span
              key={kindLabel}
              className={[
                'text-[10px] font-medium tracking-[0.28em] uppercase text-txt-secondary leading-none',
                'animate-fade-in',
              ].join(' ')}
            >
              {kindLabel}
            </span>
          </>
        )}
      </nav>

      <button
        type="button"
        onClick={onClose}
        disabled={disabled}
        aria-label="Close drawer"
        className={[
          'inline-flex items-center justify-center h-8 w-8 rounded-md shrink-0',
          'text-txt-muted hover:text-txt-primary hover:bg-surface-raised/60',
          'transition-colors duration-150 ease-out',
          'disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
        ].join(' ')}
      >
        <X aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
      </button>
    </header>
  )
}

/* ── Kind picker ─────────────────────────────────────────────────────────
 * Three vertical "channel" cards. Numbered eyebrow on the left, icon-well
 * + label + description on the right. The whole row is the click target.
 * Hover lifts the icon-well's tint and the label weight; focus-visible
 * carries the kraken outline so keyboard users get the same affordance.
 * ──────────────────────────────────────────────────────────────────── */

interface KindPickerProps {
  onPick: (kind: TaxEntryKind) => void
}

function KindPicker({ onPick }: KindPickerProps): JSX.Element {
  return (
    <div className="px-6 py-7 flex flex-col gap-7 animate-fade-in">
      <div className="flex flex-col gap-2.5">
        <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-txt-muted">
          New Entry
        </span>
        <h2 className="text-[22px] leading-[1.2] tracking-tight font-semibold text-txt-primary">
          What are you adding?
        </h2>
        <p className="text-[13px] leading-relaxed text-txt-secondary max-w-[44ch]">
          Choose the channel — you can fill in the details next.
        </p>
      </div>

      <ul role="list" className="flex flex-col gap-2.5">
        {KIND_ORDER.map((k) => {
          const cfg = KIND_CONFIG[k]
          return (
            <li key={k}>
              <button
                type="button"
                onClick={() => onPick(k)}
                className={[
                  'group w-full text-left',
                  'flex items-center gap-4 px-4 py-4',
                  'rounded-[10px] border border-surface-border bg-surface-raised/15',
                  'transition-[background-color,border-color,transform] duration-150 ease-out',
                  'hover:bg-surface-raised/35 hover:border-kraken/40',
                  'active:scale-[0.995]',
                  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
                ].join(' ')}
              >
                {/* Channel number — instrument-grade eyebrow on the left */}
                <span
                  aria-hidden="true"
                  data-numeric
                  className={[
                    'font-mono text-[11px] tracking-tight leading-none w-6 shrink-0',
                    'text-txt-muted group-hover:text-kraken/85',
                    'transition-colors duration-150 ease-out',
                  ].join(' ')}
                >
                  {cfg.channel}
                </span>

                {/* Icon well — square hairline-ringed tint, matches Toast */}
                <span
                  aria-hidden="true"
                  className={[
                    'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[7px]',
                    'ring-1 ring-kraken/20 bg-kraken/10',
                    'transition-[background-color,box-shadow] duration-150 ease-out',
                    'group-hover:bg-kraken/15 group-hover:ring-kraken/35',
                  ].join(' ')}
                >
                  <cfg.Icon
                    strokeWidth={1.75}
                    className={[
                      'h-4 w-4 text-kraken/85',
                      'transition-colors duration-150 ease-out',
                      'group-hover:text-kraken',
                    ].join(' ')}
                  />
                </span>

                {/* Label + description column */}
                <span className="flex-1 min-w-0 flex flex-col gap-1">
                  <span
                    className={[
                      'text-[14px] tracking-tight font-medium leading-none',
                      'text-txt-primary',
                    ].join(' ')}
                  >
                    {cfg.picker.label}
                  </span>
                  <span className="text-[12px] tracking-tight leading-snug text-txt-muted">
                    {cfg.picker.description}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ── Entry form ──────────────────────────────────────────────────────────
 * Stacked field rows. Each FieldRow owns its eyebrow, control slot, and
 * (optional) helper or error line. Inputs are hairline-bordered transparent
 * surfaces. The amount input uses tabular-nums + monospaced font so it
 * lines up with EntryList's amount column when the user mentally maps
 * "what I just typed" to "what shows up in the ledger".
 *
 * Footer is sticky to the drawer's bottom (via flex layout + the body's
 * overflow-y-auto). Cancel ghost on the left, Save kraken on the right.
 * Saving collapses Save into a Loader2 spinner + "Saving…" copy.
 * ──────────────────────────────────────────────────────────────────── */

interface EntryFormProps {
  kind: TaxEntryKind
  values: FormValues
  bind: <K extends keyof FormValues>(field: K) => {
    value: string
    onChange: (
      ev: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
    ) => void
    onBlur: () => void
  }
  showError: (field: keyof FormValues) => string | undefined
  isEdit: boolean
  saving: boolean
  onSubmit: (ev: FormEvent<HTMLFormElement>) => void
  onCancel: () => void
  attachments: TaxAttachment[]
  onAttachmentUploaded: (attachment: TaxAttachment) => void
  onAttachmentRemove: (id: string) => void
  onAttachmentError: (message: string) => void
  onAttachmentView?: (id: string) => void
}

function EntryForm({
  kind,
  values,
  bind,
  showError,
  isEdit,
  saving,
  onSubmit,
  onCancel,
  attachments,
  onAttachmentUploaded,
  onAttachmentRemove,
  onAttachmentError,
  onAttachmentView,
}: EntryFormProps): JSX.Element {
  const cfg = KIND_CONFIG[kind]

  /* Type options come from the kind's allowed list, sorted by their
     human-readable label so the dropdown reads alphabetically. The "other"
     fallback is preserved at the end as a stable last-resort. */
  const typeOptions = useMemo(() => {
    const items = cfg.types
      .map((t) => ({ value: t, label: TYPE_LABELS[t] ?? t }))
      .sort((a, b) => {
        if (a.value === 'other') return 1
        if (b.value === 'other') return -1
        return a.label.localeCompare(b.label)
      })
    return items
  }, [cfg.types])

  const descBinding = bind('description')
  const amountBinding = bind('amount')
  const dateBinding = bind('date')
  const typeBinding = bind('type')
  const notesBinding = bind('notes')

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col min-h-full animate-fade-in"
    >
      {/* Title row — restated inside the body so the user knows which
          channel they're filling in even if they scrolled the breadcrumb
          out of view (drawer is 480px wide; not a real risk on most
          screens, but the type rhythm wants this anchor). */}
      <div className="px-6 pt-7 pb-5 flex flex-col gap-2">
        <span className="text-[10px] font-medium tracking-[0.28em] uppercase text-kraken/85">
          Channel {cfg.channel}
        </span>
        <h2 className="text-[22px] leading-[1.2] tracking-tight font-semibold text-txt-primary">
          {isEdit ? `Edit ${cfg.picker.label.toLowerCase()}` : `Add ${cfg.picker.label.toLowerCase()}`}
        </h2>
      </div>

      {/* Field stack */}
      <div className="px-6 pb-6 flex flex-col gap-5">
        <FieldRow
          id="entry-description"
          label="Description"
          eyebrow="Field 01"
          required
          error={showError('description')}
          counter={`${values.description.length}/${DESC_MAX}`}
        >
          <input
            id="entry-description"
            type="text"
            inputMode="text"
            autoComplete="off"
            maxLength={DESC_MAX}
            placeholder={
              kind === 'income'
                ? 'e.g. November salary'
                : kind === 'tax_paid'
                  ? 'e.g. Q2 BAS payment'
                  : 'e.g. Cursor Pro subscription'
            }
            disabled={saving}
            {...descBinding}
            className={inputClass(showError('description'))}
            aria-invalid={!!showError('description')}
          />
        </FieldRow>

        {/* Amount + Date — paired on a row when there's room, stacked on
            narrow widths. The drawer is 480px so this almost always
            renders side-by-side. */}
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-5">
          <FieldRow
            id="entry-amount"
            label="Amount"
            eyebrow="Field 02 · AUD"
            required
            error={showError('amount')}
          >
            <div className="relative">
              <span
                aria-hidden="true"
                className={[
                  'absolute left-3 top-1/2 -translate-y-1/2',
                  'font-mono text-[12px] tracking-tight text-txt-muted leading-none',
                ].join(' ')}
              >
                $
              </span>
              <input
                id="entry-amount"
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                placeholder="0.00"
                disabled={saving}
                {...amountBinding}
                className={[
                  inputClass(showError('amount')),
                  'pl-7 font-mono tabular-nums',
                ].join(' ')}
                aria-invalid={!!showError('amount')}
              />
            </div>
          </FieldRow>

          <FieldRow
            id="entry-date"
            label="Date"
            eyebrow="Field 03"
            required
            error={showError('date')}
          >
            <input
              id="entry-date"
              type="date"
              disabled={saving}
              {...dateBinding}
              className={[
                inputClass(showError('date')),
                'font-mono tabular-nums w-[160px]',
                // Native date pickers in dark mode get their indicator
                // hard-coded to black — the filter recolours it to match
                // the rest of the surface. Quiet, but it's the difference
                // between "instrument" and "default form".
                '[&::-webkit-calendar-picker-indicator]:invert-[0.7]',
                '[&::-webkit-calendar-picker-indicator]:opacity-60',
                '[&::-webkit-calendar-picker-indicator]:hover:opacity-100',
                '[&::-webkit-calendar-picker-indicator]:cursor-pointer',
              ].join(' ')}
              aria-invalid={!!showError('date')}
            />
          </FieldRow>
        </div>

        <FieldRow
          id="entry-type"
          label="Type"
          eyebrow="Field 04"
          required
          error={showError('type')}
        >
          <select
            id="entry-type"
            disabled={saving}
            {...typeBinding}
            className={[
              inputClass(showError('type')),
              'pr-9 cursor-pointer',
            ].join(' ')}
            aria-invalid={!!showError('type')}
          >
            {typeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </FieldRow>

        <FieldRow
          id="entry-notes"
          label="Notes"
          eyebrow="Field 05 · Optional"
          error={showError('notes')}
          counter={values.notes.length > 0 ? `${values.notes.length}/${NOTES_MAX}` : undefined}
        >
          <textarea
            id="entry-notes"
            rows={3}
            placeholder="Anything worth remembering at tax time."
            maxLength={NOTES_MAX}
            disabled={saving}
            {...notesBinding}
            className={[
              inputClass(showError('notes')),
              'resize-none leading-relaxed py-2.5',
            ].join(' ')}
            aria-invalid={!!showError('notes')}
          />
        </FieldRow>

        {/* Attachments — Task 22 wires the real upload + view flow.
            FileDropZone owns the upload, AttachmentChip renders one row
            per uploaded file with an X for removal. The dropzone
            collapses to a compact "+ Add more" pill when chips are
            already present so the form's vertical rhythm doesn't
            balloon mid-flow. */}
        <FieldRow
          id="entry-attachments"
          label="Attachments"
          eyebrow={
            attachments.length > 0
              ? `Field 06 · ${attachments.length} attached`
              : 'Field 06 · Optional'
          }
        >
          <div className="flex flex-col gap-2.5">
            {attachments.length > 0 && (
              <ul
                role="list"
                className="flex flex-wrap gap-2"
                aria-label="Attached files"
              >
                {attachments.map((a) => (
                  <li key={a.id}>
                    <AttachmentChip
                      attachment={a}
                      onView={() => onAttachmentView?.(a.id)}
                      onRemove={() => onAttachmentRemove(a.id)}
                    />
                  </li>
                ))}
              </ul>
            )}
            <FileDropZone
              parentKind={kind}
              compact={attachments.length > 0}
              onUploaded={onAttachmentUploaded}
              onError={onAttachmentError}
            />
          </div>
        </FieldRow>
      </div>

      {/* Spacer — pushes the footer to the bottom when the form is short.
          On taller screens this collapses to zero and the footer abuts
          the last field naturally. */}
      <div className="flex-1" />

      <DrawerFooter
        saving={saving}
        isEdit={isEdit}
        onCancel={onCancel}
      />
    </form>
  )
}

/* ── Field row primitive ─────────────────────────────────────────────────
 * Eyebrow above, label inline, control below, helper / error / counter on
 * a tertiary line. The structure is deliberately rigid so eight fields
 * stack into a calm column without each one inventing its own layout.
 * ──────────────────────────────────────────────────────────────────── */

interface FieldRowProps {
  id: string
  label: string
  eyebrow: string
  required?: boolean
  error?: string
  counter?: string
  children: React.ReactNode
}

function FieldRow({
  id,
  label,
  eyebrow,
  required = false,
  error,
  counter,
  children,
}: FieldRowProps): JSX.Element {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[9.5px] font-medium tracking-[0.24em] uppercase text-txt-muted leading-none">
        {eyebrow}
      </span>
      <label
        htmlFor={id}
        className={[
          'text-[13px] tracking-tight font-medium leading-none',
          'text-txt-primary',
        ].join(' ')}
      >
        {label}
        {required && (
          <span aria-hidden="true" className="ml-1 text-kraken/70">
            *
          </span>
        )}
      </label>
      <div className="mt-1">{children}</div>

      {/* Error or counter — same line, error wins. Counter sits right-
          aligned to keep the eye on the field, not the meta. */}
      {(error || counter) && (
        <div className="flex items-center justify-between gap-3 mt-0.5 min-h-[14px]">
          {error ? (
            <span
              className={[
                'flex items-baseline gap-1.5',
                'text-[10px] font-medium tracking-[0.22em] uppercase leading-none text-loss/85',
              ].join(' ')}
              role="alert"
            >
              <span>Error</span>
              <span aria-hidden="true" className="text-loss/55">
                ·
              </span>
              <span className="normal-case tracking-tight font-normal text-[11.5px] text-loss/95">
                {error}
              </span>
            </span>
          ) : (
            <span aria-hidden="true" />
          )}
          {counter && !error && (
            <span
              data-numeric
              className="font-mono text-[10.5px] tracking-tight leading-none text-txt-muted/70"
            >
              {counter}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Footer ──────────────────────────────────────────────────────────────
 * Hairline top border. Cancel ghost button on the left (text-only, no
 * border), Save kraken-filled on the right. Save shows a Loader2 spinner
 * and disables both buttons while saving.
 * ──────────────────────────────────────────────────────────────────── */

interface DrawerFooterProps {
  saving: boolean
  isEdit: boolean
  onCancel: () => void
}

function DrawerFooter({ saving, isEdit, onCancel }: DrawerFooterProps): JSX.Element {
  return (
    <footer
      className={[
        'sticky bottom-0 flex items-center justify-end gap-3',
        'px-6 py-4 border-t border-surface-border bg-surface',
      ].join(' ')}
    >
      <button
        type="button"
        onClick={onCancel}
        disabled={saving}
        className={[
          'inline-flex items-center justify-center px-3.5 py-2 rounded-md',
          'text-[12.5px] font-medium tracking-tight text-txt-secondary',
          'transition-colors duration-150 ease-out',
          'hover:text-txt-primary hover:bg-surface-raised/40',
          'disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
        ].join(' ')}
      >
        Cancel
      </button>
      <button
        type="submit"
        disabled={saving}
        className={[
          'group inline-flex items-center gap-2 rounded-md px-4 py-2',
          'bg-kraken text-white text-[12.5px] font-medium tracking-tight',
          'shadow-[0_1px_0_0_rgba(255,255,255,0.08)_inset,0_8px_22px_-12px_rgba(123,97,255,0.7)]',
          'transition-[background-color,transform,box-shadow] duration-150 ease-out',
          'hover:bg-kraken-light active:scale-[0.985]',
          'disabled:opacity-70 disabled:cursor-not-allowed disabled:hover:bg-kraken disabled:active:scale-100',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
        ].join(' ')}
      >
        {saving ? (
          <>
            <Loader2
              aria-hidden="true"
              strokeWidth={2}
              className="h-3.5 w-3.5 animate-spin"
            />
            <span>Saving…</span>
          </>
        ) : (
          <span>{isEdit ? 'Save changes' : 'Save entry'}</span>
        )}
      </button>
    </footer>
  )
}

/* ── Input class helper ──────────────────────────────────────────────────
 * Centralised so every input (text, number, date, select, textarea) shares
 * the same hairline-bordered transparent surface and focus treatment. The
 * `error` class state escalates the border to loss-red so the validation
 * message and the field share a visual identity.
 * ──────────────────────────────────────────────────────────────────── */

function inputClass(error: string | undefined): string {
  return [
    'w-full px-3 py-2 rounded-md',
    'border bg-transparent',
    'text-[13px] tracking-tight text-txt-primary placeholder:text-txt-muted/85',
    'transition-[border-color,background-color] duration-150 ease-out',
    'focus:bg-surface-raised/30 focus:outline-none',
    'disabled:opacity-60 disabled:cursor-not-allowed',
    error
      ? 'border-loss/55 hover:border-loss/70 focus:border-loss'
      : 'border-surface-border hover:border-kraken/40 focus:border-kraken/60',
  ].join(' ')
}
