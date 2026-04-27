import { LayoutDashboard, Receipt } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import SignOutButton from './SignOutButton'

type View = 'dashboard' | 'tax'

interface SideRailProps {
  view: View
  onChangeView: (view: View) => void
  onSignedOut: () => void
}

interface NavItem {
  id: View
  label: string
  Icon: LucideIcon
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { id: 'tax', label: 'Tax', Icon: Receipt },
]

/**
 * SideRail — primary left navigation.
 *
 * Restrained, "instrument-grade" rail anchored on type hierarchy and a
 * single colour accent. Active state communicates anchoring through a
 * subtle kraken-tinted surface and brightened glyph weight rather than
 * a coloured edge stripe. Linear/Arc school: spacing and typography
 * carry the structure.
 */
export default function SideRail({ view, onChangeView, onSignedOut }: SideRailProps) {
  return (
    <nav
      aria-label="Primary"
      className="w-[200px] h-screen shrink-0 flex flex-col bg-surface border-r border-surface-border select-none"
    >
      {/* Wordmark — small geometric mark + restrained type. Subtle but premium. */}
      <header className="px-5 pt-7 pb-8">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="relative inline-flex h-6 w-6 items-center justify-center"
          >
            <span className="absolute inset-0 rounded-[7px] bg-kraken/15" />
            <svg
              viewBox="0 0 16 16"
              className="relative h-3.5 w-3.5 text-kraken"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M3 3v10" />
              <path d="M3 8l4.5 -5" />
              <path d="M3 8l4.5 5" />
              <path d="M11 5v6" />
              <path d="M11 11l2 2" />
            </svg>
          </span>
          <span className="text-[13px] font-medium tracking-[0.18em] uppercase text-kraken">
            Kraken
          </span>
        </div>
      </header>

      {/* Eyebrow label */}
      <div className="px-5 pb-2">
        <span className="text-[10px] font-medium tracking-[0.22em] uppercase text-txt-muted">
          Navigation
        </span>
      </div>

      {/* Items */}
      <ul role="list" className="px-2.5 flex flex-col gap-0.5">
        {NAV_ITEMS.map(({ id, label, Icon }) => {
          const isActive = view === id
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => onChangeView(id)}
                aria-current={isActive ? 'page' : undefined}
                className={[
                  'group relative w-full flex items-center gap-3 rounded-md px-3 py-2.5',
                  'text-[13px] font-medium tracking-tight',
                  'transition-[background-color,color] duration-150 ease-out',
                  'focus-visible:outline-none',
                  isActive
                    ? 'bg-kraken/10 text-txt-primary'
                    : 'text-txt-secondary hover:bg-surface-raised/50 hover:text-txt-primary',
                ].join(' ')}
              >
                <Icon
                  aria-hidden="true"
                  strokeWidth={1.75}
                  className={[
                    'h-[17px] w-[17px] shrink-0',
                    'transition-colors duration-150 ease-out',
                    isActive
                      ? 'text-kraken'
                      : 'text-txt-muted group-hover:text-txt-secondary',
                  ].join(' ')}
                />
                <span className="leading-none">{label}</span>
              </button>
            </li>
          )
        })}
      </ul>

      {/* Spacer — pushes sign-out to the floor */}
      <div className="flex-1" />

      {/* Footer — hairline divider + relocated sign-out */}
      <footer className="px-5 py-5 border-t border-surface-border/70">
        <SignOutButton onSignedOut={onSignedOut} />
      </footer>
    </nav>
  )
}
