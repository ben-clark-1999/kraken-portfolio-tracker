import { NavLink } from 'react-router-dom'
import { Layers, Coins, Wallet, Trophy, type LucideIcon } from 'lucide-react'

interface Route {
  to: string
  label: string
  Icon: LucideIcon
  hint: string
}

const ROUTES: Route[] = [
  { to: '/combined',   label: 'Combined',   Icon: Layers, hint: 'All sources' },
  { to: '/crypto',     label: 'Crypto',     Icon: Coins,  hint: 'Kraken pairs' },
  { to: '/up',         label: 'UP Bank',    Icon: Wallet, hint: 'AUD transactions' },
  { to: '/strategies', label: 'Strategies', Icon: Trophy, hint: 'Paper-trading sandbox' },
]

export default function SidebarNav() {
  return (
    <nav
      aria-label="Primary"
      className="flex flex-col w-52 shrink-0 border-r border-surface-border h-screen sticky top-0 bg-surface"
    >
      <div className="px-4 pt-5 pb-7 flex items-center gap-2.5">
        <span aria-hidden="true" className="relative inline-flex h-2.5 w-2.5">
          <span className="absolute inset-0 rounded-full bg-kraken" />
          <span className="absolute inset-0 rounded-full bg-kraken/40 blur-[3px]" />
        </span>
        <span className="text-[13px] font-mono font-medium tracking-tight text-txt-primary lowercase">
          kraken
        </span>
      </div>

      <div className="px-2 flex flex-col gap-0.5">
        {ROUTES.map(({ to, label, Icon, hint }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [
                'group relative flex items-center gap-2.5 px-2.5 py-2 rounded-md',
                'transition-[background-color,color] duration-150 ease-out',
                isActive
                  ? 'bg-kraken/12 text-txt-primary'
                  : 'text-txt-secondary hover:bg-surface-hover/60 hover:text-txt-primary',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  aria-hidden="true"
                  strokeWidth={1.5}
                  className={[
                    'h-4 w-4 shrink-0 transition-colors duration-150',
                    isActive ? 'text-kraken-light' : 'text-txt-muted group-hover:text-txt-secondary',
                  ].join(' ')}
                />
                <span className="text-sm font-medium tracking-tight">
                  {label}
                </span>
                <span
                  className={[
                    'ml-auto h-1 w-1 rounded-full transition-[opacity,transform] duration-200 ease-out',
                    isActive ? 'bg-kraken opacity-100 scale-100' : 'bg-kraken opacity-0 scale-50',
                  ].join(' ')}
                  aria-hidden="true"
                />
                <span className="sr-only">{hint}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>

      <div className="mt-auto px-4 pb-4 pt-4 border-t border-surface-border/60">
        <p className="text-[10px] font-mono tracking-wide text-txt-muted uppercase leading-tight">
          Portfolio
          <br />
          <span className="text-txt-secondary normal-case tracking-tight">tracker</span>
        </p>
      </div>
    </nav>
  )
}
