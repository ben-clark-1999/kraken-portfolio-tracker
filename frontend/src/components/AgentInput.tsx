import { useEffect, useRef, useState } from 'react'
import { Sparkles, ArrowUp } from 'lucide-react'

type Variant = 'topbar' | 'hero' | 'docked'

interface Props {
  onSubmit: (content: string) => void
  onFocus?: () => void
  panelOpen?: boolean
  variant?: Variant
}

interface VariantStyles {
  container: string
  icon: string
  input: string
  send: string
  sendIcon: string
  showKbdHint: boolean
}

const VARIANT_STYLES: Record<Variant, VariantStyles> = {
  topbar: {
    container: 'w-full max-w-sm rounded-md border bg-surface/40 px-3 py-1.5',
    icon: 'h-3.5 w-3.5',
    input: 'text-sm',
    send: 'h-6 w-6 rounded',
    sendIcon: 'h-3.5 w-3.5',
    showKbdHint: true,
  },
  hero: {
    container: 'w-full max-w-[640px] rounded-full border bg-surface-raised px-5 py-3',
    icon: 'h-5 w-5',
    input: 'text-base',
    send: 'h-9 w-9 rounded-full',
    sendIcon: 'h-4 w-4',
    showKbdHint: false,
  },
  docked: {
    container: 'w-full rounded-full border bg-surface-raised px-4 py-2.5',
    icon: 'h-4 w-4',
    input: 'text-[15px]',
    send: 'h-8 w-8 rounded-full',
    sendIcon: 'h-4 w-4',
    showKbdHint: false,
  },
}

export default function AgentInput({
  onSubmit,
  onFocus,
  panelOpen,
  variant = 'topbar',
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)
  const styles = VARIANT_STYLES[variant]

  useEffect(() => {
    if (variant !== 'topbar') return
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        onFocus?.()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onFocus, panelOpen, variant])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) return
    onSubmit(trimmed)
    setValue('')
  }

  const hasContent = value.trim().length > 0

  return (
    <form
      onSubmit={handleSubmit}
      className={[
        'group relative flex items-center gap-2',
        styles.container,
        'transition-[border-color,background-color,box-shadow] duration-200 ease-out',
        focused
          ? 'border-kraken/60 bg-surface-raised shadow-[0_0_0_3px_rgba(123,97,255,0.10)]'
          : 'border-surface-border hover:border-kraken/40',
      ].join(' ')}
    >
      <Sparkles
        aria-hidden="true"
        strokeWidth={1.5}
        className={[
          'shrink-0 transition-colors duration-200',
          styles.icon,
          focused ? 'text-kraken-light' : 'text-txt-muted group-hover:text-txt-secondary',
        ].join(' ')}
      />

      <input
        ref={inputRef}
        type="text"
        autoFocus={variant === 'hero'}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onFocus={() => {
          setFocused(true)
          onFocus?.()
        }}
        onBlur={() => setFocused(false)}
        placeholder="Ask about your portfolio…"
        aria-label="Ask the portfolio agent"
        className={[
          'flex-1 min-w-0 bg-transparent text-txt-primary placeholder:text-txt-muted outline-none caret-kraken-light',
          styles.input,
        ].join(' ')}
      />

      {hasContent ? (
        <button
          type="submit"
          aria-label="Send"
          className={[
            'inline-flex items-center justify-center bg-kraken text-white',
            styles.send,
            'transition-[background-color,transform] duration-150 ease-out',
            'hover:bg-kraken-light active:scale-95',
          ].join(' ')}
        >
          <ArrowUp className={styles.sendIcon} strokeWidth={2.25} />
        </button>
      ) : styles.showKbdHint ? (
        <kbd
          aria-hidden="true"
          className={[
            'hidden sm:inline font-mono text-[10px] tracking-tight',
            'rounded border border-surface-border px-1.5 py-0.5',
            'text-txt-muted bg-surface/60',
            'transition-opacity duration-200',
            panelOpen ? 'opacity-40' : 'opacity-100',
          ].join(' ')}
        >
          ⌘K
        </kbd>
      ) : null}
    </form>
  )
}
