import AgentMessage from './AgentMessage'
import AgentToolStatus from './AgentToolStatus'
import AgentHITL from './AgentHITL'
import type { AgentMessage as AgentMessageType, ToolActivity, HITLState } from '../types/agent'

interface Props {
  messages: AgentMessageType[]
  activeTools: ToolActivity[]
  hitl: HITLState | null
  onRespondHITL: (approved: boolean) => void
}

export default function AgentConversation({ messages, activeTools, hitl, onRespondHITL }: Props) {
  return (
    <div className="space-y-6">
      {messages.map((m) => (
        <AgentMessage key={m.id} message={m} />
      ))}
      {activeTools.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {activeTools.map((t) => (
            <AgentToolStatus key={t.tool} activity={t} />
          ))}
        </div>
      )}
      {hitl?.pending && <AgentHITL hitl={hitl} onRespond={onRespondHITL} />}
    </div>
  )
}
