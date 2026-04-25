import type { ToolActivity } from '../types/agent'

interface Props {
  activity: ToolActivity
}

function formatToolName(name: string): string {
  return name.replace(/^get_/, '').replace(/_/g, '_')
}

function formatParams(params: Record<string, unknown>): string {
  const entries = Object.entries(params)
  if (entries.length === 0) return ''
  return `(${entries.map(([, v]) => String(v)).join(', ')})`
}

export default function AgentToolStatus({ activity }: Props) {
  return (
    <div className="flex items-center gap-2 text-[11px] font-mono text-txt-muted overflow-hidden">
      <span className="whitespace-nowrap shrink-0">
        fetching → {formatToolName(activity.tool)}{formatParams(activity.params)}
      </span>
      <div className="flex-1 h-[2px] bg-surface-border rounded-full overflow-hidden">
        <div className="h-full bg-kraken/40 rounded-full animate-progress" />
      </div>
    </div>
  )
}
