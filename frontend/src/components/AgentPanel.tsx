import type { AgentMessage as AgentMessageType, ToolActivity, HITLState } from '../types/agent'
import AgentMessage from './AgentMessage'
import AgentToolStatus from './AgentToolStatus'
import AgentHITL from './AgentHITL'
import NewConversationButton from './NewConversationButton'
import { useEffect, useRef } from 'react'

interface Props {
  messages: AgentMessageType[]
  activeTools: ToolActivity[]
  hitl: HITLState | null
  thinking: boolean
  onRespondHITL: (approved: boolean) => void
  onNewConversation: () => void
  onSubmit: (content: string) => void
}

const EXAMPLE_QUERIES = [
  "How's my portfolio doing?",
  "Am I approaching any CGT thresholds?",
  "What's changed since last week?",
  "Would I have been better off just holding ETH?",
]

export default function AgentPanel({
  messages,
  activeTools,
  hitl,
  thinking,
  onRespondHITL,
  onNewConversation,
  onSubmit,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, activeTools, hitl, thinking])

  const isEmpty = messages.length === 0 && !thinking

  return (
    <aside className="fixed inset-y-0 right-0 w-[400px] z-50 flex flex-col bg-surface border-l border-surface-border shadow-2xl overflow-y-auto">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between">
        <NewConversationButton onClick={onNewConversation} />
      </div>

      <div className="px-4 pb-6">
        {isEmpty ? (
          <div className="pt-8 space-y-3">
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onSubmit(q)}
                className="block w-full text-left text-sm text-txt-muted hover:text-txt-secondary transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-4 pt-2">
            {messages.map((msg) => (
              <AgentMessage key={msg.id} message={msg} />
            ))}

            {activeTools.map((tool) => (
              <AgentToolStatus key={tool.tool} activity={tool} />
            ))}

            {hitl && (
              <AgentHITL hitl={hitl} onRespond={onRespondHITL} />
            )}

            {thinking && activeTools.length === 0 && !hitl && (
              <div className="h-4 w-16 bg-surface-border rounded animate-pulse-subtle" />
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </aside>
  )
}
