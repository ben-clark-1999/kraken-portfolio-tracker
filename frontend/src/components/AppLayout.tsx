import { ReactNode } from 'react'
import SidebarNav from './SidebarNav'

interface Props {
  children: ReactNode
  /** Slot for the agent chat panel — passed in from App.tsx so layout
   *  doesn't own conversation state. */
  chatPanel?: ReactNode
}

export default function AppLayout({ children, chatPanel }: Props) {
  return (
    <div className="flex min-h-screen bg-surface text-txt-primary">
      <SidebarNav />
      <main className="flex-1 overflow-auto">{children}</main>
      {chatPanel && (
        <aside className="w-96 border-l border-surface-border">{chatPanel}</aside>
      )}
    </div>
  )
}
