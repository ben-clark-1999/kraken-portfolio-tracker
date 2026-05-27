import { Check, X } from 'lucide-react'
import type { HITLState } from '../types/agent'

interface Props {
  hitl: HITLState
  onRespond: (approved: boolean) => void
}

function formatDuration(ms: number): string {
  if (!ms || ms < 0) return ''
  if (ms < 1000) return `~${ms}ms`
  const s = Math.round(ms / 1000)
  if (s < 60) return `~${s}s`
  const m = Math.round(s / 60)
  return `~${m}m`
}

export default function AgentHITL({ hitl, onRespond }: Props) {
  const duration = formatDuration(hitl.estimated_duration_ms)
  return (
    <div
      role="alertdialog"
      aria-label="Approve tool call"
      className="rounded-xl border border-kraken/30 bg-kraken/[0.06] p-4 space-y-3"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-[15px] leading-relaxed text-txt-primary font-sans flex-1">
          {hitl.reason}
        </p>
        {duration && (
          <span className="shrink-0 text-xs text-txt-muted font-mono mt-0.5">{duration}</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onRespond(true)}
          autoFocus
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-kraken text-white text-sm font-medium hover:bg-kraken-light active:scale-[0.98] transition-[background-color,transform] duration-150"
        >
          <Check className="w-4 h-4" />
          Proceed
        </button>
        <button
          type="button"
          onClick={() => onRespond(false)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-surface-raised border border-surface-border text-txt-primary text-sm font-medium hover:bg-surface-hover active:scale-[0.98] transition-[background-color,transform] duration-150"
        >
          <X className="w-4 h-4" />
          Cancel
        </button>
      </div>
    </div>
  )
}
