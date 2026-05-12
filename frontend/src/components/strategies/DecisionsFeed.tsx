import { useEffect, useMemo, useState } from 'react'
import { ChevronRight } from 'lucide-react'

import { fetchDecisions } from '../../api/strategies'
import type { AgentDecision } from '../../types/strategies'

interface Props {
  strategyId: string
  n?: number
}

const AUD_2 = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function formatCost(value: string): string {
  const n = Number(value)
  if (!Number.isFinite(n) || n === 0) return '$0.00'
  if (n < 0.01) return '< $0.01'
  return AUD_2.format(n)
}

function formatAbsoluteTs(iso: string): string {
  return new Date(iso).toLocaleString('en-AU', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatRelative(iso: string, now: number): string {
  const diff = Math.max(0, now - new Date(iso).getTime())
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 48) return `${hr}h ago`
  const day = Math.floor(hr / 24)
  return `${day}d ago`
}

function Chip({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode
  tone?: 'neutral' | 'kraken' | 'red'
}) {
  const cls =
    tone === 'kraken'
      ? 'bg-kraken/15 text-kraken-light ring-1 ring-kraken/25'
      : tone === 'red'
      ? 'bg-loss/15 text-loss ring-1 ring-loss/30'
      : 'bg-surface-border/60 text-txt-secondary ring-1 ring-surface-border'
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide ${cls}`}>
      {children}
    </span>
  )
}

function ToolCall({ call }: { call: AgentDecision['tool_calls'][number] }) {
  const args = call.args ? JSON.stringify(call.args) : ''
  return (
    <div className="font-mono text-[11px] text-txt-secondary px-2.5 py-1.5 rounded bg-surface/70 ring-1 ring-surface-border/60 overflow-x-auto whitespace-nowrap">
      <span className="text-kraken-light">{call.tool}</span>
      <span className="text-txt-muted">(</span>
      <span className="text-txt-primary">{args}</span>
      <span className="text-txt-muted">)</span>
    </div>
  )
}

function DecisionRow({
  decision,
  open,
  onToggle,
  now,
}: {
  decision: AgentDecision
  open: boolean
  onToggle: () => void
  now: number
}) {
  const mode = decision.execution_mode
  const isLlm = mode === 'llm_agent'
  const hasError = Boolean(decision.error)
  const reasoning = decision.agent_output ?? (isLlm ? null : 'Scheduled buy / rebalance.')

  return (
    <li
      className={[
        'border-b border-surface-border/60 last:border-b-0',
        hasError ? 'bg-loss/[0.04]' : '',
      ].join(' ')}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-surface-hover/40 transition-colors"
      >
        <ChevronRight
          aria-hidden="true"
          strokeWidth={1.5}
          className={['h-3.5 w-3.5 mt-1 text-txt-muted shrink-0 transition-transform', open ? 'rotate-90' : ''].join(' ')}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Chip>{decision.trigger_event.type}</Chip>
            <Chip tone={isLlm ? 'kraken' : 'neutral'}>{isLlm ? 'LLM' : 'RULES'}</Chip>
            {isLlm && (
              <span className="text-[11px] font-mono tabular-nums text-txt-muted">
                {formatCost(decision.cost_aud)}
              </span>
            )}
            {hasError && <Chip tone="red">ERROR</Chip>}
            <span
              title={formatAbsoluteTs(decision.created_at)}
              className="ml-auto text-[11px] text-txt-muted tabular-nums cursor-help"
            >
              {formatRelative(decision.created_at, now)}
            </span>
          </div>

          {!open && reasoning && (
            <p className="mt-1.5 text-xs text-txt-secondary leading-relaxed truncate">
              {reasoning}
            </p>
          )}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 pl-[2.625rem] space-y-3">
          {reasoning && (
            <p className="text-xs text-txt-secondary leading-relaxed whitespace-pre-wrap">
              {reasoning}
            </p>
          )}

          {decision.tool_calls.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-medium uppercase tracking-wider text-txt-muted">
                Tool calls
              </p>
              {decision.tool_calls.map((c, i) => (
                <ToolCall key={i} call={c} />
              ))}
            </div>
          )}

          {hasError && (
            <p className="text-xs text-loss leading-relaxed">
              <span className="font-medium">Error:</span> {decision.error}
            </p>
          )}

          {isLlm && (
            <div className="flex gap-4 text-[10px] font-mono uppercase tracking-wider text-txt-muted">
              {decision.model && <span>{decision.model}</span>}
              <span>in {decision.input_tokens.toLocaleString('en-AU')}t</span>
              <span>out {decision.output_tokens.toLocaleString('en-AU')}t</span>
              {decision.latency_ms !== null && <span>{decision.latency_ms}ms</span>}
            </div>
          )}
        </div>
      )}
    </li>
  )
}

export default function DecisionsFeed({ strategyId, n = 50 }: Props) {
  const [decisions, setDecisions] = useState<AgentDecision[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openIds, setOpenIds] = useState<Set<string>>(new Set())
  const now = useMemo(() => Date.now(), [decisions])

  useEffect(() => {
    let cancelled = false
    setDecisions(null)
    setError(null)
    fetchDecisions(strategyId, n)
      .then(data => { if (!cancelled) setDecisions(data) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true }
  }, [strategyId, n])

  if (error) {
    return (
      <p className="px-4 py-6 text-sm text-loss" role="status" aria-live="polite">
        Decisions unavailable: {error}
      </p>
    )
  }

  if (decisions === null) {
    return (
      <div className="px-4 py-4 space-y-1.5" aria-busy="true">
        <div className="h-12 rounded bg-surface-border/40 animate-pulse-subtle" />
        <div className="h-12 rounded bg-surface-border/30 animate-pulse-subtle" />
        <div className="h-12 rounded bg-surface-border/20 animate-pulse-subtle" />
      </div>
    )
  }

  if (decisions.length === 0) {
    return (
      <p className="px-4 py-6 text-sm text-txt-muted leading-relaxed">
        No decisions yet. The first one lands on the next trigger fire.
      </p>
    )
  }

  return (
    <ul className="divide-y divide-surface-border/60">
      {decisions.map(d => (
        <DecisionRow
          key={d.id}
          decision={d}
          now={now}
          open={openIds.has(d.id)}
          onToggle={() =>
            setOpenIds(prev => {
              const next = new Set(prev)
              if (next.has(d.id)) next.delete(d.id)
              else next.add(d.id)
              return next
            })
          }
        />
      ))}
    </ul>
  )
}
