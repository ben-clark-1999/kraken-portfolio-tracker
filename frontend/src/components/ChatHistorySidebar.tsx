import { Plus, MessageSquare } from 'lucide-react'
import type { PastSession } from '../hooks/useAgentChat'

interface Props {
  sessions: PastSession[]
  activeSessionId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}

interface Group { label: string; sessions: PastSession[] }

function groupSessions(sessions: PastSession[]): Group[] {
  const now = Date.now()
  const DAY = 24 * 60 * 60 * 1000
  const groups: Record<string, PastSession[]> = {
    Today: [],
    Yesterday: [],
    'Last 7 days': [],
    Older: [],
  }
  for (const s of sessions) {
    const age = now - new Date(s.last_active_at).getTime()
    if (age < DAY) groups.Today.push(s)
    else if (age < 2 * DAY) groups.Yesterday.push(s)
    else if (age < 7 * DAY) groups['Last 7 days'].push(s)
    else groups.Older.push(s)
  }
  return (Object.entries(groups) as [string, PastSession[]][])
    .filter(([, list]) => list.length > 0)
    .map(([label, list]) => ({ label, sessions: list }))
}

export default function ChatHistorySidebar({ sessions, activeSessionId, onSelect, onNew }: Props) {
  const groups = groupSessions(sessions)
  return (
    <aside className="w-60 shrink-0 border-r border-surface-border flex flex-col h-full">
      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-surface-raised border border-surface-border text-sm text-txt-primary hover:bg-surface-hover transition-colors duration-200"
        >
          <Plus className="w-4 h-4" />
          New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-4">
        {groups.length === 0 && (
          <p className="text-xs text-txt-muted px-2 pt-2">No past conversations yet.</p>
        )}
        {groups.map((g) => (
          <div key={g.label}>
            <h3 className="px-2 mb-1 text-[11px] uppercase tracking-wider text-txt-muted font-medium">
              {g.label}
            </h3>
            <ul className="space-y-0.5">
              {g.sessions.map((s) => {
                const isActive = s.id === activeSessionId
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(s.id)}
                      className={[
                        'w-full text-left px-2 py-1.5 rounded text-sm flex items-start gap-2',
                        'transition-colors duration-200',
                        isActive
                          ? 'bg-surface-raised text-txt-primary'
                          : 'text-txt-secondary hover:bg-surface-raised/60 hover:text-txt-primary',
                      ].join(' ')}
                    >
                      <MessageSquare className="w-3.5 h-3.5 mt-0.5 shrink-0 text-txt-muted" />
                      <span className="truncate">{s.title}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
    </aside>
  )
}
