import { useCallback, useId, useRef, useState } from 'react'
import type {
  ChangeEvent,
  DragEvent as ReactDragEvent,
  JSX,
  KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import { Plus, UploadCloud } from 'lucide-react'

import { uploadAttachment } from '../../api/tax'
import type { TaxAttachment, TaxEntryKind } from '../../types/tax'

/* ──────────────────────────────────────────────────────────────────────────
 * FileDropZone — the only place in the Tax Hub the user attaches files.
 *
 * Two states for one component:
 *
 *   • Empty (no chips above it) — the dropzone takes most of the available
 *     width, sits on a dashed hairline outline, and presents a calm icon
 *     well + monospaced eyebrow + helper line. Hover lifts the kraken
 *     tint; drag-enter promotes the eyebrow to "RELEASE TO UPLOAD" and
 *     pulses the well subtly. The whole region is a labelled file picker
 *     — keyboard users can focus + Enter to open the OS file dialog.
 *   • Has-files (chips already placed by the parent above) — the parent
 *     passes nothing about that to us. WE simply collapse to a thin
 *     "Add more" row. The smaller surface is still drag-and-droppable
 *     and click-to-pick — same affordance, less visual weight.
 *
 * Validation:
 *   - Size > 10 MB → onError("filename is over 10 MB")
 *   - Content type outside {image/jpeg, image/png, image/webp,
 *     application/pdf} → onError("filename is not a supported file type")
 *   - The file picker uses an `accept` filter as a hint; we still
 *     validate after drop because `accept` only filters the picker.
 *
 * Upload flow:
 *   - Each accepted file is uploaded in parallel via uploadAttachment(
 *     parentKind, null, file). parent_id is always null — this is the
 *     pending-upload flow; tax_service rebinds the attachments when the
 *     entry is created.
 *   - On success, onUploaded(attachment) fires per file. The parent
 *     (EntryDrawer) collects the attachments into its own state.
 *   - On failure, onError(message) — the parent surfaces a toast.
 *
 * No left-edge accent stripes. No glassmorphism. No sparkles. The drop-
 * over highlight is the same kraken tint used everywhere else, just at
 * higher opacity.
 * ────────────────────────────────────────────────────────────────────── */

const MAX_BYTES = 10 * 1024 * 1024 // 10 MB
const ALLOWED_TYPES = new Set<string>([
  'image/jpeg',
  'image/png',
  'image/webp',
  'application/pdf',
])
const ACCEPT_ATTR = '.pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp'

export interface FileDropZoneProps {
  parentKind: TaxEntryKind
  onUploaded: (attachment: TaxAttachment) => void
  onError: (message: string) => void
  /** When true the dropzone collapses to a compact "Add more" row.
   *  Driven by the parent (EntryDrawer) based on whether attachments
   *  already exist above. */
  compact?: boolean
}

/* ── Component ──────────────────────────────────────────────────────────── */

export default function FileDropZone({
  parentKind,
  onUploaded,
  onError,
  compact = false,
}: FileDropZoneProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const inputId = useId()
  const [isDragging, setIsDragging] = useState(false)
  // We track in-flight uploads so the dropzone's eyebrow can read
  // "UPLOADING · 2 OF 3" while files are streaming. The actual chip
  // progress lives in the parent drawer; this is just the dropzone's
  // local readout.
  const [active, setActive] = useState(0)
  const [completed, setCompleted] = useState(0)

  const totalInBatch = active + completed > 0 ? active + completed : 0
  const isUploading = active > 0

  /* ── Validation + upload pipeline ─────────────────────────────────── */

  const handleFiles = useCallback(
    async (files: FileList | File[]): Promise<void> => {
      const list = Array.from(files)
      if (list.length === 0) return

      // First-pass: split into accepted / rejected with synchronous
      // validation. Rejections fire onError immediately; accepted files
      // get uploaded in parallel.
      const accepted: File[] = []
      for (const file of list) {
        if (file.size > MAX_BYTES) {
          onError(`${file.name} is over 10 MB`)
          continue
        }
        if (!ALLOWED_TYPES.has(file.type)) {
          // Some browsers omit the MIME type on drop — fall back to
          // extension-sniffing so legitimate files aren't rejected for
          // a missing header.
          const ext = file.name.toLowerCase().split('.').pop() ?? ''
          const extOk = ['pdf', 'png', 'jpg', 'jpeg', 'webp'].includes(ext)
          if (!extOk) {
            onError(`${file.name} is not a supported file type`)
            continue
          }
        }
        accepted.push(file)
      }
      if (accepted.length === 0) return

      setActive((n) => n + accepted.length)

      await Promise.all(
        accepted.map(async (file) => {
          try {
            const attachment = await uploadAttachment(parentKind, null, file)
            onUploaded(attachment)
            setCompleted((n) => n + 1)
          } catch (e) {
            onError(
              e instanceof Error
                ? `${file.name}: ${e.message}`
                : `Couldn't upload ${file.name}`,
            )
          } finally {
            setActive((n) => Math.max(0, n - 1))
          }
        }),
      )

      // Once the queue drains, reset the local readout. We delay one
      // frame so the "UPLOADED · 2 OF 2" message has time to register
      // visually before disappearing.
      requestAnimationFrame(() => {
        setActive((n) => (n === 0 ? 0 : n))
      })
    },
    [parentKind, onUploaded, onError],
  )

  /* ── Picker + drop handlers ───────────────────────────────────────── */

  function openPicker(): void {
    inputRef.current?.click()
  }

  function onInputChange(ev: ChangeEvent<HTMLInputElement>): void {
    const files = ev.target.files
    if (files && files.length > 0) {
      void handleFiles(files)
    }
    // Reset so the same file can be re-picked if the user removes it.
    ev.target.value = ''
  }

  function onDragEnter(ev: ReactDragEvent<HTMLDivElement>): void {
    ev.preventDefault()
    ev.stopPropagation()
    if (ev.dataTransfer?.types.includes('Files')) {
      setIsDragging(true)
    }
  }
  function onDragOver(ev: ReactDragEvent<HTMLDivElement>): void {
    // dragover MUST be prevented for drop to fire. The browser default is
    // to forbid the drop, which silently breaks the entire flow.
    ev.preventDefault()
    ev.stopPropagation()
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'copy'
  }
  function onDragLeave(ev: ReactDragEvent<HTMLDivElement>): void {
    ev.preventDefault()
    ev.stopPropagation()
    // Only clear when the drag actually leaves the boundary, not the
    // child layout. relatedTarget is null when leaving the window.
    const next = ev.relatedTarget as Node | null
    if (next && ev.currentTarget.contains(next)) return
    setIsDragging(false)
  }
  function onDrop(ev: ReactDragEvent<HTMLDivElement>): void {
    ev.preventDefault()
    ev.stopPropagation()
    setIsDragging(false)
    const dropped = ev.dataTransfer?.files
    if (dropped && dropped.length > 0) {
      void handleFiles(dropped)
    }
  }
  function onKeyDown(ev: ReactKeyboardEvent<HTMLDivElement>): void {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault()
      openPicker()
    }
  }

  /* ── Hidden input — shared between empty + compact states ────────── */

  const hiddenInput = (
    <input
      id={inputId}
      ref={inputRef}
      type="file"
      multiple
      accept={ACCEPT_ATTR}
      onChange={onInputChange}
      className="sr-only"
      aria-label="Choose files to attach"
    />
  )

  /* ── Compact state (used when chips already exist above) ─────────── */

  if (compact) {
    return (
      <>
        {hiddenInput}
        <div
          role="button"
          tabIndex={0}
          aria-label="Add more attachments"
          onClick={openPicker}
          onKeyDown={onKeyDown}
          onDragEnter={onDragEnter}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          data-dragging={isDragging || undefined}
          className={[
            'group inline-flex items-center gap-2 px-3 py-2 self-start',
            'rounded-md border border-dashed bg-transparent',
            'cursor-pointer select-none',
            'transition-[border-color,background-color,color] duration-150 ease-out',
            isDragging
              ? 'border-kraken/60 bg-kraken/8'
              : 'border-surface-border hover:border-kraken/40 hover:bg-surface-raised/35',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
          ].join(' ')}
        >
          <Plus
            aria-hidden="true"
            strokeWidth={2}
            className={[
              'h-3.5 w-3.5',
              isDragging ? 'text-kraken' : 'text-kraken/80 group-hover:text-kraken',
              'transition-colors duration-150 ease-out',
            ].join(' ')}
          />
          <span
            className={[
              'text-[12px] font-medium tracking-tight',
              isDragging ? 'text-txt-primary' : 'text-txt-secondary group-hover:text-txt-primary',
              'transition-colors duration-150 ease-out',
            ].join(' ')}
          >
            {isUploading ? `Uploading ${active}…` : 'Add more'}
          </span>
        </div>
      </>
    )
  }

  /* ── Empty state (the inviting hero dropzone) ────────────────────── */

  return (
    <>
      {hiddenInput}
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop files here or press Enter to choose files"
        onClick={openPicker}
        onKeyDown={onKeyDown}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        data-dragging={isDragging || undefined}
        className={[
          'group relative w-full',
          'flex flex-col items-center justify-center text-center gap-3',
          'px-6 py-7 rounded-[10px]',
          // Dashed hairline border — it's the only visual surface that
          // earns dashes in the workspace; reserved for "active drop
          // target" semantics.
          'border border-dashed bg-transparent',
          'cursor-pointer select-none',
          // Motion — kraken tint promotes on hover, deeper on drag-over.
          'transition-[border-color,background-color,box-shadow] duration-150 ease-out',
          isDragging
            ? 'border-kraken/65 bg-kraken/8 shadow-[0_0_0_3px_rgba(123,97,255,0.06)]'
            : 'border-surface-border hover:border-kraken/45 hover:bg-surface-raised/25',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kraken',
        ].join(' ')}
      >
        {/* Icon well — square hairline-ringed kraken tint, larger than
            the chips' wells so it reads as "headline" within the drop
            zone. Pulses subtly while files are uploading. */}
        <span
          aria-hidden="true"
          className={[
            'inline-flex h-11 w-11 items-center justify-center rounded-[9px]',
            'ring-1 transition-[background-color,box-shadow] duration-150 ease-out',
            isDragging
              ? 'bg-kraken/18 ring-kraken/45'
              : 'bg-kraken/10 ring-kraken/22 group-hover:bg-kraken/14 group-hover:ring-kraken/35',
            isUploading ? 'animate-pulse-subtle' : '',
          ].join(' ')}
        >
          <UploadCloud
            strokeWidth={1.6}
            className={[
              'h-5 w-5',
              isDragging ? 'text-kraken' : 'text-kraken/85 group-hover:text-kraken',
              'transition-colors duration-150 ease-out',
            ].join(' ')}
          />
        </span>

        {/* Eyebrow — instrument-grade readout. Mode-shifts when dragging
            or uploading so the user gets a confirming signal in the
            same visual slot. */}
        <span
          className={[
            'text-[10px] font-medium tracking-[0.28em] uppercase leading-none',
            'transition-colors duration-150 ease-out',
            isDragging
              ? 'text-kraken'
              : isUploading
                ? 'text-kraken/85'
                : 'text-txt-muted group-hover:text-txt-secondary',
          ].join(' ')}
        >
          {isDragging
            ? 'Release to upload'
            : isUploading
              ? `Uploading · ${completed} of ${totalInBatch}`
              : 'Drop files or click to upload'}
        </span>

        {/* Helper line — sentence-case, instrument vocabulary. Below the
            eyebrow so the eye reads readout → human description without
            re-anchoring. */}
        <span
          className={[
            'text-[12px] leading-snug tracking-tight max-w-[40ch]',
            'text-txt-muted/85',
          ].join(' ')}
        >
          PDF, JPG, PNG, WebP — up to 10 MB each.
        </span>

        {/* Tertiary hint — keyboard affordance. Tiny, monospaced, like
            a footnote on an instrument panel. Only renders when not
            dragging so the message stays uncluttered. */}
        {!isDragging && (
          <span
            data-numeric
            className={[
              'inline-flex items-center gap-1.5 mt-0.5',
              'text-[10px] tracking-[0.18em] uppercase font-mono leading-none',
              'text-txt-muted/55',
            ].join(' ')}
          >
            <kbd className="px-1.5 py-0.5 rounded-[3px] border border-surface-border/80 text-txt-muted/80 normal-case tracking-tight">
              Enter
            </kbd>
            <span aria-hidden="true">·</span>
            <span>opens picker</span>
          </span>
        )}
      </div>
    </>
  )
}
