import { NavLink } from 'react-router-dom'

const links = [
  { to: '/combined', label: 'Combined' },
  { to: '/crypto',   label: 'Crypto' },
  { to: '/up',       label: 'UP Bank' },
]

export default function SidebarNav() {
  return (
    <nav className="flex flex-col gap-1 p-3 w-44 border-r border-surface-border h-full bg-surface">
      {links.map(l => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            `px-3 py-2 rounded text-sm transition-colors ${
              isActive
                ? 'bg-kraken/20 text-txt-primary'
                : 'text-txt-secondary hover:bg-surface-hover'
            }`
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  )
}
