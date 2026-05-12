import { useEffect, useRef, useState } from 'react'
import { Sparkles, ArrowUp } from 'lucide-react'

interface Props {
  onSubmit: (content: string) => void
  onFocus: () => void
  panelOpen: boolean
}

export default function AgentInput({ onSubmit, onFocus, panelOpen }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        onFocus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onFocus, panelOpen])

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
        'group relative flex items-center gap-2 w-full max-w-sm rounded-md',
        'border bg-surface/40 px-3 py-1.5',
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
          'h-3.5 w-3.5 shrink-0 transition-colors duration-200',
          focused ? 'text-kraken-light' : 'text-txt-muted group-hover:text-txt-secondary',
        ].join(' ')}
      />

      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onFocus={() => {
          setFocused(true)
          onFocus()
        }}
        onBlur={() => setFocused(false)}
        placeholder="Ask about your portfolio…"
        aria-label="Ask the portfolio agent"
        className="flex-1 min-w-0 bg-transparent text-sm text-txt-primary placeholder:text-txt-muted outline-none caret-kraken-light"
      />

      {hasContent ? (
        <button
          type="submit"
          aria-label="Send"
          className={[
            'inline-flex h-6 w-6 items-center justify-center rounded',
            'bg-kraken text-white',
            'transition-[background-color,transform] duration-150 ease-out',
            'hover:bg-kraken-light active:scale-95',
          ].join(' ')}
        >
          <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.25} />
        </button>
      ) : (
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
      )}
    </form>
  )
}
