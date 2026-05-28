import { useSearchParams } from 'react-router-dom'

export type UpTabId = { id: string; label: string }

export const UP_TAB_IDS: readonly UpTabId[] = [
  { id: 'balance', label: 'Balance' },
  { id: 'spending', label: 'Spending' },
  { id: 'transactions', label: 'Transactions' },
  { id: 'ask', label: 'Ask AI' },
] as const

const DEFAULT_ID = 'balance'

export function useActiveUpTab(): { active: string; setActive: (id: string) => void } {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const active = UP_TAB_IDS.some((t) => t.id === raw) ? (raw as string) : DEFAULT_ID
  const setActive = (id: string) => {
    const next = new URLSearchParams(params)
    next.set('tab', id)
    setParams(next, { replace: true })
  }
  return { active, setActive }
}

export default function UpTabBar() {
  const { active, setActive } = useActiveUpTab()
  return (
    <div
      role="tablist"
      aria-label="Up Bank sections"
      className="border-b border-surface-border flex items-end gap-6 overflow-x-auto whitespace-nowrap"
    >
      {UP_TAB_IDS.map((t) => {
        const isActive = t.id === active
        return (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={isActive}
            onClick={() => setActive(t.id)}
            className={[
              'relative py-3 text-sm font-medium transition-colors duration-200',
              isActive ? 'text-txt-primary' : 'text-txt-muted hover:text-txt-secondary',
            ].join(' ')}
          >
            {t.label}
            <span
              aria-hidden
              className={[
                'absolute left-0 right-0 -bottom-px h-0.5 rounded-full transition-opacity duration-200',
                isActive ? 'bg-kraken opacity-100' : 'opacity-0',
              ].join(' ')}
            />
          </button>
        )
      })}
    </div>
  )
}
