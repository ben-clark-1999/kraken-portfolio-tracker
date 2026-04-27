import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { JSX } from 'react'
import { Check, AlertCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/* ──────────────────────────────────────────────────────────────────────────
 * Toast — instrument-grade status callouts.
 *
 * Design rationale: this is not a generic toast. It rejects the canonical
 * "rounded card with a coloured left stripe + emoji" silhouette in favour of
 * something that feels native to this dashboard — a hairline-bordered
 * surface anchored on a tinted glyph well, a small monospaced eyebrow
 * (SAVED / FAILED) like an instrument-panel readout, and the message
 * carrying the primary type weight. Variant signal lives in the icon-well
 * tint and the eyebrow colour — never as an accent stripe.
 *
 * Architecture: a module-level pub/sub store. `useToast()` is a thin
 * wrapper exposing `showToast`; `ToastContainer` subscribes via
 * `useSyncExternalStore` so any component anywhere in the tree can fire a
 * toast without a Provider in the tree.
 * ────────────────────────────────────────────────────────────────────── */

export type ToastVariant = 'success' | 'error'

export interface ToastOptions {
  variant: ToastVariant
  message: string
  /** ms before auto-dismiss, default 4000 */
  duration?: number
}

interface ToastRecord {
  id: number
  variant: ToastVariant
  message: string
  duration: number
}

/* ── Store ──────────────────────────────────────────────────────────────── */

type Listener = () => void

let nextId = 1
let toasts: ReadonlyArray<ToastRecord> = []
const listeners = new Set<Listener>()

function emit(): void {
  for (const l of listeners) l()
}

function addToast(opts: ToastOptions): number {
  const record: ToastRecord = {
    id: nextId++,
    variant: opts.variant,
    message: opts.message,
    duration: opts.duration ?? 4000,
  }
  toasts = [...toasts, record]
  emit()
  return record.id
}

function removeToast(id: number): void {
  const next = toasts.filter((t) => t.id !== id)
  if (next.length === toasts.length) return
  toasts = next
  emit()
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): ReadonlyArray<ToastRecord> {
  return toasts
}

/* ── Public hook ────────────────────────────────────────────────────────── */

export function useToast(): { showToast: (opts: ToastOptions) => void } {
  const showToast = useCallback((opts: ToastOptions) => {
    addToast(opts)
  }, [])
  return { showToast }
}

/* ── Variant tokens ─────────────────────────────────────────────────────── */

interface VariantConfig {
  Icon: LucideIcon
  /** Tiny instrument-panel eyebrow */
  label: string
  /** Class fragments for the icon-well + eyebrow tint */
  wellBg: string
  wellRing: string
  iconColor: string
  eyebrowColor: string
}

const VARIANTS: Record<ToastVariant, VariantConfig> = {
  success: {
    Icon: Check,
    label: 'SAVED',
    wellBg: 'bg-kraken/12',
    wellRing: 'ring-kraken/25',
    iconColor: 'text-kraken',
    eyebrowColor: 'text-kraken/85',
  },
  error: {
    Icon: AlertCircle,
    label: 'FAILED',
    wellBg: 'bg-loss/12',
    wellRing: 'ring-loss/25',
    iconColor: 'text-loss',
    eyebrowColor: 'text-loss/85',
  },
}

/* ── Container ──────────────────────────────────────────────────────────── */

/**
 * Mounted once near the App root. Renders the live toast stack in the
 * bottom-right, newest visually on top of the stack (which means it
 * appears above earlier toasts, drawing the eye to the latest event).
 *
 * z-[60] sits above EntryDrawer (z-50) so toasts are never occluded by
 * a panel that may have triggered them.
 */
export function ToastContainer(): JSX.Element {
  const items = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  return (
    <div
      // The container itself is non-interactive — only individual toasts
      // capture clicks. `pointer-events-none` lets the user keep clicking
      // through the empty space around toasts.
      className="pointer-events-none fixed bottom-6 right-6 z-[60] flex w-[min(22rem,calc(100vw-2rem))] flex-col-reverse gap-2"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
      aria-atomic="false"
    >
      {items.map((t) => (
        <ToastItem key={t.id} record={t} onDismiss={() => removeToast(t.id)} />
      ))}
    </div>
  )
}

/* ── Item ───────────────────────────────────────────────────────────────── */

interface ToastItemProps {
  record: ToastRecord
  onDismiss: () => void
}

function ToastItem({ record, onDismiss }: ToastItemProps): JSX.Element {
  const config = VARIANTS[record.variant]
  const { Icon } = config

  // Three-phase lifecycle: 'enter' (mount) → 'open' (post-paint) → 'exit'
  // (animating away). Driven by data-state, styled via CSS transitions.
  const [state, setState] = useState<'enter' | 'open' | 'exit'>('enter')
  const dismissTimer = useRef<number | null>(null)
  const exitTimer = useRef<number | null>(null)

  // Promote 'enter' → 'open' on the next frame so the transition fires.
  useEffect(() => {
    const raf = requestAnimationFrame(() => setState('open'))
    return () => cancelAnimationFrame(raf)
  }, [])

  const beginExit = useCallback(() => {
    if (exitTimer.current !== null) return
    setState('exit')
    // Match the CSS exit duration below (150ms).
    exitTimer.current = window.setTimeout(onDismiss, 160)
  }, [onDismiss])

  // Auto-dismiss timer.
  useEffect(() => {
    dismissTimer.current = window.setTimeout(beginExit, record.duration)
    return () => {
      if (dismissTimer.current !== null) window.clearTimeout(dismissTimer.current)
      if (exitTimer.current !== null) window.clearTimeout(exitTimer.current)
    }
  }, [record.duration, beginExit])

  return (
    <div
      role="status"
      data-state={state}
      className={[
        // Pointer events re-enabled here so the toast itself is clickable.
        'pointer-events-auto relative w-full',
        // Surface — hairline, no left-stripe accent. Subtle backdrop blur
        // gives an atmospheric float over busy chart content.
        'rounded-[10px] border border-surface-border bg-surface/95 backdrop-blur-md',
        // Soft drop-shadow for separation; gives a premium "lifted"
        // feeling without ever looking like glass.
        'shadow-[0_8px_24px_-12px_rgba(0,0,0,0.6),0_2px_6px_-2px_rgba(0,0,0,0.4)]',
        // Motion — opacity + translate driven by data-state below.
        'transition-[opacity,transform] duration-200 ease-out will-change-transform',
        // Initial / exit positioning: slide up from 8px below, fade in.
        'data-[state=enter]:opacity-0 data-[state=enter]:translate-y-2',
        'data-[state=open]:opacity-100 data-[state=open]:translate-y-0',
        'data-[state=exit]:opacity-0 data-[state=exit]:translate-y-1',
        // Faster, sharper exit per motion ref.
        'data-[state=exit]:duration-150 data-[state=exit]:ease-in',
      ].join(' ')}
    >
      {/* The whole card is a dismiss button — full-bleed click target with
          a real, focusable, keyboard-accessible button so screen readers
          and keyboard users get the same affordance as mouse users. */}
      <button
        type="button"
        onClick={beginExit}
        aria-label={`Dismiss notification: ${record.message}`}
        className={[
          'group flex w-full items-start gap-3 text-left',
          'rounded-[10px] px-3.5 py-3 cursor-pointer',
          'transition-colors duration-150 ease-out',
          'hover:bg-surface-raised/30',
        ].join(' ')}
      >
        {/* Icon well — variant punctuation lives here. Square with a soft
            tinted fill + 1px hairline ring. Echoes the kraken wordmark
            treatment in SideRail. */}
        <span
          aria-hidden="true"
          className={[
            'mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-[6px]',
            'ring-1',
            config.wellBg,
            config.wellRing,
          ].join(' ')}
        >
          <Icon strokeWidth={2.25} className={['h-3.5 w-3.5', config.iconColor].join(' ')} />
        </span>

        {/* Type column — eyebrow over message, hierarchy via weight + size. */}
        <span className="min-w-0 flex-1">
          <span
            className={[
              'block text-[10px] font-medium tracking-[0.22em] uppercase leading-none',
              config.eyebrowColor,
            ].join(' ')}
          >
            {config.label}
          </span>
          <span className="mt-1.5 block text-[13px] leading-snug text-txt-primary tracking-tight">
            {record.message}
          </span>
        </span>
      </button>
    </div>
  )
}
