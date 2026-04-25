import { useRef, useEffect } from 'react'

interface Props {
  onSubmit: (content: string) => void
  onFocus: () => void
  panelOpen: boolean
}

export default function AgentInput({ onSubmit, onFocus, panelOpen }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        if (panelOpen) {
          // Toggle off is handled by parent
          onFocus()
        } else {
          inputRef.current?.focus()
          onFocus()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onFocus, panelOpen])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const input = inputRef.current
    if (!input || !input.value.trim()) return
    onSubmit(input.value.trim())
    input.value = ''
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2 flex-1 max-w-sm">
      <input
        ref={inputRef}
        type="text"
        placeholder="Ask about your portfolio..."
        onFocus={onFocus}
        className="w-full bg-transparent text-sm text-txt-primary placeholder:text-txt-muted outline-none"
      />
      <kbd className="hidden sm:inline text-[10px] text-txt-muted border border-surface-border rounded px-1.5 py-0.5 font-mono">
        ⌘K
      </kbd>
    </form>
  )
}
