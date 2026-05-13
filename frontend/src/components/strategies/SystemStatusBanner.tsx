import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'

import { fetchHealth } from '../../api/strategies'
import type { HealthResponse } from '../../types/strategies'

interface Props {
  refreshSeconds?: number
}

type Level = 'green' | 'amber' | 'red' | 'unknown'

interface Anomaly {
  key: string
  text: string
  severity: 'amber' | 'red'
}

const AMBER = '#F59E0B' // not in palette — used inline so banner reads as warning
const FEED_AMBER_S = 30
const FEED_RED_S = 300
// Cross-region deploy (Railway US-East ↔ Supabase Sydney) has a ~200ms
// baseline round trip per query. p99 routinely sits in the 400-900ms band
// without anything actually being wrong. The threshold was originally 500ms
// (a sensible value for a same-machine local backend) — bump it so the
// banner only fires when latency is genuinely degraded vs typical.
const DB_RED_MS = 1500

function classify(h: HealthResponse): { level: Level; anomalies: Anomaly[] } {
  const anomalies: Anomaly[] = []

  for (const [pair, feed] of Object.entries(h.ws_feed)) {
    const age = feed.age_s
    if (age === null) {
      anomalies.push({ key: `feed:${pair}`, severity: 'red', text: `${pair} feed never connected` })
    } else if (age > FEED_RED_S) {
      anomalies.push({ key: `feed:${pair}`, severity: 'red', text: `${pair} feed silent for ${Math.round(age)}s` })
    } else if (age > FEED_AMBER_S) {
      anomalies.push({ key: `feed:${pair}`, severity: 'amber', text: `${pair} feed stale (${Math.round(age)}s)` })
    }
  }

  if (h.db.write_latency_ms_p99 > DB_RED_MS) {
    anomalies.push({
      key: 'db:latency',
      severity: 'red',
      text: `DB write p99 ${h.db.write_latency_ms_p99}ms (> ${DB_RED_MS}ms)`,
    })
  }

  for (const s of h.strategies) {
    if (s.status === 'paused') {
      anomalies.push({ key: `paused:${s.id}`, severity: 'amber', text: `${s.name} paused` })
    }
  }

  const hasRed = anomalies.some(a => a.severity === 'red')
  const hasAmber = anomalies.some(a => a.severity === 'amber')
  const level: Level = hasRed ? 'red' : hasAmber ? 'amber' : 'green'
  return { level, anomalies }
}

function statusText(level: Level, n: number): string {
  if (level === 'green') return 'Healthy'
  if (level === 'red') return `Critical · ${n}`
  if (level === 'amber') return `Degraded · ${n}`
  return 'Status…'
}

function Dot({ level }: { level: Level }) {
  const base = 'h-1.5 w-1.5 rounded-full shrink-0'
  if (level === 'green') return <span aria-hidden="true" className={`${base} bg-profit`} />
  if (level === 'red') return <span aria-hidden="true" className={`${base} bg-loss`} />
  if (level === 'amber') {
    return <span aria-hidden="true" className={base} style={{ background: AMBER }} />
  }
  return <span aria-hidden="true" className={`${base} bg-txt-muted/40`} />
}

export default function SystemStatusBanner({ refreshSeconds = 15 }: Props) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [expanded, setExpanded] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let cancelled = false

    const tick = async () => {
      try {
        const data = await fetchHealth()
        if (!cancelled) setHealth(data)
      } catch {
        if (!cancelled) setHealth(null)
      }
    }

    tick()
    const id = window.setInterval(tick, Math.max(2, refreshSeconds) * 1000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [refreshSeconds])

  useEffect(() => {
    if (!expanded) return
    function onDown(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setExpanded(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setExpanded(false)
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [expanded])

  const { level, anomalies } = health ? classify(health) : { level: 'unknown' as Level, anomalies: [] }
  const text = statusText(level, anomalies.length)

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        aria-haspopup="true"
        className={[
          'inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-medium',
          'border border-surface-border bg-surface hover:bg-surface-hover transition-colors',
          level === 'green' ? 'text-txt-secondary' : 'text-txt-primary',
        ].join(' ')}
      >
        <Dot level={level} />
        <span className="tracking-tight">{text}</span>
        <ChevronDown
          aria-hidden="true"
          strokeWidth={1.5}
          className={['h-3 w-3 text-txt-muted transition-transform', expanded ? 'rotate-180' : ''].join(' ')}
        />
      </button>

      {expanded && (
        <div
          role="dialog"
          aria-label="System status details"
          className="absolute right-0 top-[calc(100%+6px)] z-40 w-80 rounded-lg border border-surface-border bg-surface-raised shadow-2xl"
        >
          <div className="px-4 py-3 border-b border-surface-border/60 flex items-center gap-2">
            <Dot level={level} />
            <p className="text-xs font-medium uppercase tracking-wider text-txt-secondary">
              {text}
            </p>
          </div>

          {!health && (
            <p className="px-4 py-3 text-xs text-txt-muted">Health endpoint unreachable.</p>
          )}

          {health && anomalies.length === 0 && (
            <p className="px-4 py-3 text-xs text-txt-muted leading-relaxed">
              All feeds fresh. Database within latency budget. No paused strategies.
            </p>
          )}

          {anomalies.length > 0 && (
            <ul className="py-1.5 max-h-72 overflow-y-auto">
              {anomalies.map(a => (
                <li
                  key={a.key}
                  className="flex items-start gap-2.5 px-4 py-1.5 text-xs"
                >
                  <span
                    aria-hidden="true"
                    className="h-1.5 w-1.5 rounded-full mt-1.5 shrink-0"
                    style={{
                      background: a.severity === 'red' ? '#EF4444' : AMBER,
                    }}
                  />
                  <span className="text-txt-secondary leading-relaxed">{a.text}</span>
                </li>
              ))}
            </ul>
          )}

          {health && (
            <div className="px-4 py-2 border-t border-surface-border/60 text-[10px] font-mono uppercase tracking-wider text-txt-muted flex justify-between">
              <span>{Object.keys(health.ws_feed).length} feeds</span>
              <span>p99 {health.db.write_latency_ms_p99}ms</span>
              <span>{health.executor.open_orders} open</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
