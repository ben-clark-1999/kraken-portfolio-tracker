import { useEffect, useRef } from 'react'
import { Loader2 } from 'lucide-react'
import AgentMessage from './AgentMessage'
import AgentToolStatus from './AgentToolStatus'
import AgentHITL from './AgentHITL'
import type { AgentMessage as AgentMessageType, ToolActivity, HITLState } from '../types/agent'

interface Props {
  messages: AgentMessageType[]
  activeTools: ToolActivity[]
  hitl: HITLState | null
  thinking: boolean
  onRespondHITL: (approved: boolean) => void
}

export default function AgentConversation({ messages, activeTools, hitl, thinking, onRespondHITL }: Props) {
  const endRef = useRef<HTMLDivElement>(null)
  const lastContent = messages[messages.length - 1]?.content ?? ''

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, lastContent])

  const latestTool = activeTools[activeTools.length - 1] ?? null

  return (
    <div className="space-y-6">
      {messages.map((m) => (
        <AgentMessage key={m.id} message={m} />
      ))}
      {latestTool ? (
        <AgentToolStatus activity={latestTool} />
      ) : thinking ? (
        <span className="inline-flex items-center gap-2 text-sm text-txt-muted">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-kraken/70" aria-hidden />
          <span>Thinking…</span>
        </span>
      ) : null}
      {hitl?.pending && <AgentHITL hitl={hitl} onRespond={onRespondHITL} />}
      <div ref={endRef} aria-hidden />
    </div>
  )
}
