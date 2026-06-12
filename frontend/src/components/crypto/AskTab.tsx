import { Sparkles } from 'lucide-react'
import AgentInput from '../AgentInput'
import AgentConversation from '../AgentConversation'
import SuggestionPills from '../SuggestionPills'
import ChatHistorySidebar from '../ChatHistorySidebar'
import { useAgentChat } from '../../hooks/useAgentChat'

const SUGGESTIONS = [
  'Is my portfolio good?',
  "What's my biggest holding?",
  'Show my recent purchases',
  'Am I up this month?',
]

export default function AskTab() {
  const agent = useAgentChat()
  const empty = agent.messages.length === 0

  return (
    <div className="flex gap-6 h-[calc(100vh-12rem)]">
      <ChatHistorySidebar
        sessions={agent.sessions}
        activeSessionId={agent.sessionId}
        onSelect={agent.loadSession}
        onNew={agent.newConversation}
        onDelete={agent.deleteSession}
      />

      <div className="flex-1 min-w-0 relative flex flex-col overflow-hidden">
        {empty ? (
          <div className="relative overflow-hidden h-full flex items-center justify-center">
            <div
              aria-hidden
              className="absolute top-0 right-0 w-[420px] h-[420px] rounded-full bg-kraken/30 blur-3xl opacity-30 pointer-events-none"
            />
            <div
              aria-hidden
              className="absolute bottom-0 left-0 w-[420px] h-[420px] rounded-full bg-kraken-dark/25 blur-3xl opacity-30 pointer-events-none"
            />
            <div className="relative w-full max-w-[640px] flex flex-col items-center text-center px-6">
              <div className="bg-kraken/10 p-3 rounded-2xl mb-6">
                <Sparkles className="w-6 h-6 text-kraken" />
              </div>
              <h1 className="text-3xl font-semibold text-txt-primary tracking-tight">
                How can I help with your portfolio?
              </h1>
              <p className="text-txt-muted mt-3 text-base">
                Ask anything about your holdings, P&amp;L, or recent purchases.
              </p>
              <div className="w-full mt-8">
                <AgentInput variant="hero" onSubmit={(text) => agent.send(text)} />
              </div>
              <SuggestionPills suggestions={SUGGESTIONS} onPick={(s) => agent.send(s)} />
            </div>
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-y-auto">
            <div className="max-w-[720px] mx-auto pb-32">
              <AgentConversation
                messages={agent.messages}
                activeTools={agent.activeTools}
                hitl={agent.hitl}
                thinking={agent.thinking}
                onRespondHITL={agent.respondHITL}
              />
            </div>
            <div className="sticky bottom-4 max-w-[720px] mx-auto">
              <AgentInput variant="docked" onSubmit={(text) => agent.send(text)} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
