import Markdown from 'react-markdown'
import type { AgentMessage as AgentMessageType } from '../types/agent'

interface Props {
  message: AgentMessageType
}

export default function AgentMessage({ message }: Props) {
  if (message.role === 'user') {
    return (
      <p className="text-xs text-txt-muted font-sans">
        {message.content}
      </p>
    )
  }

  return (
    <div className="text-[15px] leading-relaxed text-txt-primary font-sans prose-invert max-w-none">
      <Markdown
        components={{
          table: (props) => (
            <table className="text-sm font-mono tabular-nums w-full" {...props} />
          ),
          th: (props) => (
            <th className="text-left text-xs text-txt-muted font-medium pb-1 pr-3" {...props} />
          ),
          td: (props) => (
            <td className="text-sm text-txt-primary py-0.5 pr-3 tabular-nums" {...props} />
          ),
        }}
      >
        {message.content}
      </Markdown>
      {message.streaming && (
        <span className="inline-block w-1.5 h-4 bg-txt-muted animate-pulse-subtle ml-0.5 align-text-bottom" />
      )}
    </div>
  )
}
