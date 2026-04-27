import { useEffect, useRef, useState } from 'react'
import type { JSX, MouseEvent as ReactMouseEvent } from 'react'
import { AlertCircle, FileText, Loader2, Paperclip, X } from 'lucide-react'

import type { TaxAttachment } from '../../types/tax'

/* ──────────────────────────────────────────────────────────────────────────
 * AttachmentChip — compact pill representing one uploaded file.
 *
 * Two render modes share this single component so the visual language is
 * identical in both surfaces and the user reads them as the same kind of
 * object:
 *
 *   1. Interactive (EntryDrawer): the chip is a button. Clicking opens the
 *      signed URL in a new tab; an optional X icon removes the attachment
 *      from the in-progress entry. While uploading we show a Loader2 and
 *      (optionally) a thin progress bar; on error we replace the size text
 *      with the failure message and recolour the icon-well loss-red.
 *   2. Display-only (EntryList rows): the chip is a button too — but only
 *      for the click-to-view affordance. No remove glyph, no progress, no
 *      error state (those entries have already been persisted; their
 *      attachments are in the "done" terminal state from the row's POV).
 *
 * Geometry: hairline-bordered surface, square icon-well on the left, two
 * stacked text lines (filename truncated · size or status eyebrow), and an
 * optional X dismiss-button on the right. Echoes Toast's silhouette so the
 * eye reads "small status object, instrument-grade".
 *
 * The "done" eyebrow is monospaced uppercase tracking-wide caps —
 * "PDF · 2.3 MB" or "JPEG · 480 KB" — so the chip carries the same readout
 * vocabulary as the rest of the workspace's metadata.
 *
 * No left-edge accent stripes. No glassmorphism. The kraken tint is the
 * only purple in the chip, and it lives in the icon well + eyebrow. The
 * loss-red equivalent appears only when state.kind === 'error'.
 * ────────────────────────────────────────────────────────────────────── */

export type ChipState =
  | { kind: 'uploading'; progress?: number }
  | { kind: 'done' }
  | { kind: 'error'; message: string }

export interface AttachmentChipProps {
  attachment: TaxAttachment
  /** Defaults to a synthetic 'done' state when omitted. */
  state?: ChipState
  onView: () => void
  /** Omit when the chip lives inside EntryList — those rows don't allow
   *  removal (the attachment is bound to a persisted entry). */
  onRemove?: () => void
  /** Default true. False makes the chip a static information surface — no
   *  hover, no click handlers — used for read-only contexts that still
   *  want the same silhouette. */
  interactive?: boolean
}

/* ── Helpers ──────────────────────────────────────────────────────────── */

/** Compact byte-size formatter — "740 KB", "2.3 MB", "11 MB", "1.4 GB".
 *  Goes to one decimal in MB+ and rounds to integers in KB so the eye
 *  reads it as an instrument readout, not a long decimal. */
function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  if (bytes < 1024 * 1024 * 1024) {
    const mb = bytes / (1024 * 1024)
    // One decimal under 10 MB so small files keep their precision; integer
    // above that so the column reads cleanly when many chips stack.
    return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`
  }
  const gb = bytes / (1024 * 1024 * 1024)
  return `${gb < 10 ? gb.toFixed(1) : Math.round(gb)} GB`
}

/** Reduce a content-type to a four-letter code for the eyebrow.
 *  "application/pdf" → "PDF", "image/jpeg" → "JPEG", etc. */
function shortType(contentType: string): string {
  if (!contentType) return 'FILE'
  const subtype = contentType.split('/')[1] ?? contentType
  // Strip suffixes like "+xml", "vnd.something" prefixes.
  const cleaned = subtype.split(';')[0].trim()
  return cleaned.toUpperCase().replace(/^VND\./, '').slice(0, 6)
}

/* ── Component ──────────────────────────────────────────────────────────── */

export default function AttachmentChip({
  attachment,
  state,
  onView,
  onRemove,
  interactive = true,
}: AttachmentChipProps): JSX.Element {
  const effective: ChipState = state ?? { kind: 'done' }
  const isUploading = effective.kind === 'uploading'
  const isError = effective.kind === 'error'
  const isDone = effective.kind === 'done'

  const sizeText = formatBytes(attachment.size_bytes)
  const typeText = shortType(attachment.content_type)

  /* The container is a button when interactive AND not in an upload-in-
     progress / error state. When uploading we keep the chip non-clickable
     (the URL doesn't exist yet). When erroring, the user can still click
     to dismiss / retry on the parent's side, but for now we treat it as
     informational only — onView would 404. */
  const clickable = interactive && isDone

  return (
    <div
      data-state={effective.kind}
      className={[
        'group inline-flex items-stretch max-w-[280px] rounded-md',
        'border bg-transparent overflow-hidden',
        'transition-[border-color,background-color,opacity] duration-150 ease-out',
        // Default border + hover treatment by state
        isError
          ? 'border-loss/55'
          : isUploading
            ? 'border-kraken/40 animate-pulse-subtle'
            : interactive
              ? 'border-surface-border hover:border-kraken/40 hover:bg-surface-raised/40'
              : 'border-surface-border',
      ].join(' ')}
      title={attachment.filename}
    >
      {/* Click target — covers the icon well + filename column. The
          remove-X (when present) sits outside this button so the click
          targets are physically distinct. */}
      <ChipContent
        attachment={attachment}
        sizeText={sizeText}
        typeText={typeText}
        state={effective}
        clickable={clickable}
        interactive={interactive}
        onView={onView}
      />

      {onRemove && (
        <RemoveButton
          onRemove={onRemove}
          disabled={isUploading}
          filename={attachment.filename}
        />
      )}
    </div>
  )
}

/* ── Chip content (icon well + text column) ───────────────────────────── */

interface ChipContentProps {
  attachment: TaxAttachment
  sizeText: string
  typeText: string
  state: ChipState
  clickable: boolean
  interactive: boolean
  onView: () => void
}

function ChipContent({
  attachment,
  sizeText,
  typeText,
  state,
  clickable,
  interactive,
  onView,
}: ChipContentProps): JSX.Element {
  const isError = state.kind === 'error'
  const isUploading = state.kind === 'uploading'

  const content = (
    <>
      {/* Icon well — square, hairline-ringed, kraken-tinted. Matches Toast
          + EntryDrawer's KindPicker iconography so the family resembles. */}
      <span
        aria-hidden="true"
        className={[
          'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-[5px] ring-1',
          isError
            ? 'bg-loss/12 ring-loss/30'
            : 'bg-kraken/10 ring-kraken/22 group-hover:bg-kraken/15 group-hover:ring-kraken/35',
          'transition-[background-color,box-shadow] duration-150 ease-out',
        ].join(' ')}
      >
        {isUploading ? (
          <Loader2
            strokeWidth={2}
            className="h-3 w-3 text-kraken/85 animate-spin"
          />
        ) : isError ? (
          <AlertCircle
            strokeWidth={2}
            className="h-3 w-3 text-loss"
          />
        ) : (
          <FileText
            strokeWidth={1.75}
            className="h-3 w-3 text-kraken/85 group-hover:text-kraken transition-colors duration-150 ease-out"
          />
        )}
      </span>

      {/* Text column — filename then size eyebrow. Filename truncates
          with ellipsis when long; the title attribute on the wrapper
          carries the full name for hover. */}
      <span className="min-w-0 flex flex-col gap-0.5 items-start">
        <span
          className={[
            'block text-[12px] tracking-tight leading-none truncate max-w-[180px]',
            isError ? 'text-loss/95' : 'text-txt-primary',
          ].join(' ')}
        >
          {attachment.filename}
        </span>
        <span
          className={[
            'flex items-baseline gap-1 leading-none',
            'text-[9px] font-medium tracking-[0.22em] uppercase font-mono',
          ].join(' ')}
        >
          {isError ? (
            <span className="normal-case font-sans tracking-tight text-[10.5px] text-loss/85 truncate max-w-[180px]">
              {state.kind === 'error' ? state.message : ''}
            </span>
          ) : isUploading ? (
            <>
              <span className="text-kraken/85">Uploading</span>
              {state.kind === 'uploading' && typeof state.progress === 'number' && (
                <>
                  <span aria-hidden="true" className="text-txt-muted/60">
                    ·
                  </span>
                  <span
                    data-numeric
                    className="text-kraken/85 font-mono normal-case tracking-tight"
                  >
                    {Math.round(state.progress * 100)}%
                  </span>
                </>
              )}
            </>
          ) : (
            <>
              <span className="text-txt-muted">{typeText || 'FILE'}</span>
              {sizeText && (
                <>
                  <span aria-hidden="true" className="text-txt-muted/55">
                    ·
                  </span>
                  <span data-numeric className="text-txt-secondary tracking-tight normal-case">
                    {sizeText}
                  </span>
                </>
              )}
            </>
          )}
        </span>

        {/* Inline progress hairline — only when actively uploading and we
            have a numeric progress reading. Sits at the bottom of the
            text column so the chip breathes the same way at rest and
            mid-upload. */}
        {state.kind === 'uploading' && typeof state.progress === 'number' && (
          <span
            aria-hidden="true"
            className="block w-full h-px bg-surface-border/70 overflow-hidden mt-0.5 max-w-[180px]"
          >
            <span
              className="block h-full bg-kraken/70 transition-[width] duration-150 ease-out"
              style={{ width: `${Math.max(0, Math.min(1, state.progress)) * 100}%` }}
            />
          </span>
        )}
      </span>
    </>
  )

  /* When clickable we render a real button so screen readers + keyboard
     users get the same affordance. When not, render a div with the same
     padding so the geometry is consistent. */
  if (clickable) {
    return (
      <button
        type="button"
        onClick={(ev: ReactMouseEvent) => {
          ev.stopPropagation()
          onView()
        }}
        aria-label={`View ${attachment.filename}`}
        className={[
          'flex items-center gap-2 px-2 py-1.5 min-w-0 flex-1',
          'text-left',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
          'cursor-pointer',
        ].join(' ')}
      >
        {content}
      </button>
    )
  }

  return (
    <div
      className={[
        'flex items-center gap-2 px-2 py-1.5 min-w-0 flex-1',
        interactive && !isError ? '' : '',
      ].join(' ')}
      aria-label={
        isUploading
          ? `Uploading ${attachment.filename}`
          : isError
            ? `Failed to upload ${attachment.filename}`
            : attachment.filename
      }
    >
      {content}
    </div>
  )
}

/* ── Remove button (drawer-only) ──────────────────────────────────────── */

interface RemoveButtonProps {
  onRemove: () => void
  disabled: boolean
  filename: string
}

function RemoveButton({
  onRemove,
  disabled,
  filename,
}: RemoveButtonProps): JSX.Element {
  // A fade-in delay so the X doesn't startle on first paint while the chip
  // is still resolving its enter transition.
  const [mounted, setMounted] = useState(false)
  const ref = useRef<HTMLButtonElement | null>(null)
  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <button
      ref={ref}
      type="button"
      onClick={(ev) => {
        ev.stopPropagation()
        if (!disabled) onRemove()
      }}
      disabled={disabled}
      aria-label={`Remove ${filename}`}
      className={[
        'inline-flex items-center justify-center px-2 shrink-0',
        'border-l border-surface-border/70',
        'text-txt-muted hover:text-txt-primary',
        'hover:bg-surface-raised/60',
        'transition-[color,background-color,opacity] duration-150 ease-out',
        'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
        mounted ? 'opacity-100' : 'opacity-0',
      ].join(' ')}
    >
      <X aria-hidden="true" strokeWidth={1.75} className="h-3.5 w-3.5" />
    </button>
  )
}

/* ── Re-export Paperclip for parents that want the same iconography ──── */
// (The drawer's "Attachments" label uses Paperclip from lucide-react too,
// but we expose nothing — kept here for IDE auto-import affordance only
// in case a future surface wants to mirror this chip's glyph.)
export { Paperclip }
