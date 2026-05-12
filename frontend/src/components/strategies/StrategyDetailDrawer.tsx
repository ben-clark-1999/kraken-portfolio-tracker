import { useCallback, useEffect, useRef, useState } from 'react'
import { X, Pause, Play, Archive as ArchiveIcon } from 'lucide-react'

import {
  archiveStrategy,
  fetchEquityCurve,
  fetchOpenOrders,
  fetchPositions,
  fetchStrategy,
  pauseStrategy,
  resumeStrategy,
} from '../../api/strategies'
import type {
  EquityCurveResponse,
  OpenOrder,
  Strategy,
  StrategyStatus,
} from '../../types/strategies'

import EquityChart from './EquityChart'
import DecisionsFeed from './DecisionsFeed'
import PersonaChatTab from './PersonaChatTab'

interface Props {
  strategyId: string | null
  onClose: () => void
  onStateChanged?: () => void
}

type Tab = 'overview' | 'decisions' | 'chat'
type Positions = Record<string, { qty: string; avg_cost_aud: string }>

const AUD = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function fmtAud(s: string): string {
  const n = Number(s)
  return Number.isFinite(n) ? AUD.format(n) : '—'
}

function fmtQty(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  if (n === 0) return '0'
  if (Math.abs(n) >= 1) return n.toFixed(4)
  return n.toFixed(8)
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function StatusBadge({ status }: { status: StrategyStatus }) {
  const tone =
    status === 'active'
      ? 'bg-profit/15 text-profit ring-profit/30'
      : status === 'paused'
      ? 'bg-surface-border/70 text-txt-secondary ring-surface-border'
      : 'bg-transparent text-txt-muted ring-txt-muted/40'
  const label = status[0].toUpperCase() + status.slice(1)
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ring-1 ${tone}`}>
      {label}
    </span>
  )
}

function ActionButton({
  children,
  onClick,
  disabled,
  intent = 'neutral',
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  intent?: 'neutral' | 'danger'
}) {
  const tone =
    intent === 'danger'
      ? 'text-loss hover:bg-loss/10'
      : 'text-txt-secondary hover:text-txt-primary hover:bg-surface-hover'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-md border border-surface-border px-2.5 py-1 text-xs font-medium tracking-tight transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${tone}`}
    >
      {children}
    </button>
  )
}

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      role="tab"
      type="button"
      aria-selected={active}
      onClick={onClick}
      className={[
        'px-3 py-3 text-sm font-medium tracking-tight transition-colors',
        'border-b-2 -mb-px focus-visible:bg-surface-hover/50',
        active
          ? 'text-txt-primary border-kraken'
          : 'text-txt-secondary border-transparent hover:text-txt-primary',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

function OpenOrdersTable({ orders }: { orders: OpenOrder[] }) {
  if (orders.length === 0) {
    return (
      <p className="text-xs text-txt-muted leading-relaxed">
        No open orders.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[10px] font-medium uppercase tracking-wider text-txt-muted">
            <th scope="col" className="px-2 py-1.5 text-left">Pair</th>
            <th scope="col" className="px-2 py-1.5 text-left">Side</th>
            <th scope="col" className="px-2 py-1.5 text-right">Qty</th>
            <th scope="col" className="px-2 py-1.5 text-right">Limit</th>
            <th scope="col" className="px-2 py-1.5 text-right">Expires</th>
            <th scope="col" className="px-2 py-1.5 text-left">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border/60">
          {orders.map(o => (
            <tr key={o.id}>
              <td className="px-2 py-1.5 font-mono text-txt-primary">{o.pair}</td>
              <td className={`px-2 py-1.5 font-medium ${o.side === 'buy' ? 'text-profit' : 'text-loss'}`}>
                {o.side}
              </td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fmtQty(o.qty)}</td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-txt-secondary">
                {o.limit_price ? fmtAud(o.limit_price) : '—'}
              </td>
              <td className="px-2 py-1.5 text-right text-txt-muted">{fmtTime(o.expires_at)}</td>
              <td className="px-2 py-1.5 text-txt-secondary">{o.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PositionsTable({ positions }: { positions: Positions }) {
  const entries = Object.entries(positions).filter(([, p]) => Number(p.qty) !== 0)
  if (entries.length === 0) {
    return (
      <p className="text-xs text-txt-muted leading-relaxed">
        No open positions.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[10px] font-medium uppercase tracking-wider text-txt-muted">
            <th scope="col" className="px-2 py-1.5 text-left">Asset</th>
            <th scope="col" className="px-2 py-1.5 text-right">Qty</th>
            <th scope="col" className="px-2 py-1.5 text-right">Avg cost AUD</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border/60">
          {entries.map(([asset, p]) => (
            <tr key={asset}>
              <td className="px-2 py-1.5 font-mono text-txt-primary">{asset}</td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums">{fmtQty(p.qty)}</td>
              <td className="px-2 py-1.5 text-right font-mono tabular-nums text-txt-secondary">
                {fmtAud(p.avg_cost_aud)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SubsectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-medium uppercase tracking-wider text-txt-secondary mb-2">
      {children}
    </h3>
  )
}

export default function StrategyDetailDrawer({ strategyId, onClose, onStateChanged }: Props) {
  const [strategy, setStrategy] = useState<Strategy | null>(null)
  const [orders, setOrders] = useState<OpenOrder[]>([])
  const [positions, setPositions] = useState<Positions>({})
  const [equityCurve, setEquityCurve] = useState<EquityCurveResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [tab, setTab] = useState<Tab>('overview')
  const closeBtnRef = useRef<HTMLButtonElement | null>(null)

  const refresh = useCallback(async (id: string) => {
    setError(null)
    try {
      const [s, o, p, e] = await Promise.all([
        fetchStrategy(id),
        fetchOpenOrders(id),
        fetchPositions(id),
        fetchEquityCurve(id, '30d'),
      ])
      setStrategy(s)
      setOrders(o)
      setPositions(p)
      setEquityCurve(e)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    if (!strategyId) return
    let cancelled = false
    setStrategy(null)
    setOrders([])
    setPositions({})
    setEquityCurve(null)
    setError(null)
    setTab('overview')
    refresh(strategyId).then(() => {
      if (cancelled) return
    })
    return () => { cancelled = true }
  }, [strategyId, refresh])

  useEffect(() => {
    if (!strategyId) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [strategyId, onClose])

  useEffect(() => {
    if (!strategyId) return
    closeBtnRef.current?.focus()
  }, [strategyId])

  if (!strategyId) return null

  async function doAction(kind: 'pause' | 'resume' | 'archive') {
    if (!strategy || pending) return
    if (kind === 'archive') {
      const ok = window.confirm(
        `Archive ${strategy.name}? This stops trading and removes it from the leaderboard.`,
      )
      if (!ok) return
    }
    setPending(true)
    try {
      const fn = kind === 'pause' ? pauseStrategy : kind === 'resume' ? resumeStrategy : archiveStrategy
      await fn(strategy.id)
      const nextStatus: StrategyStatus = kind === 'archive' ? 'archived' : kind === 'pause' ? 'paused' : 'active'
      setStrategy({ ...strategy, status: nextStatus })
      onStateChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  const titleId = `drawer-title-${strategyId}`
  const showChatTab = strategy?.execution_mode === 'llm_agent' && Boolean(strategy.persona_key)

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close details"
        onClick={onClose}
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-fade-in cursor-default"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={[
          'absolute top-0 right-0 h-full w-full sm:max-w-3xl bg-surface',
          'border-l border-surface-border shadow-2xl overflow-y-auto',
          'flex flex-col',
        ].join(' ')}
      >
        <header className="sticky top-0 z-10 bg-surface border-b border-surface-border">
          <div className="px-6 pt-5 pb-3 flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h2 id={titleId} className="text-lg font-medium tracking-tight text-txt-primary truncate">
                  {strategy?.name ?? 'Loading…'}
                </h2>
                {strategy && <StatusBadge status={strategy.status} />}
              </div>
              {strategy?.description && (
                <p className="mt-1 text-xs text-txt-secondary leading-relaxed line-clamp-2">
                  {strategy.description}
                </p>
              )}
            </div>
            <button
              ref={closeBtnRef}
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1.5 text-txt-muted hover:text-txt-primary hover:bg-surface-hover transition-colors"
            >
              <X aria-hidden="true" strokeWidth={1.5} className="h-4 w-4" />
            </button>
          </div>

          {strategy && (
            <div className="px-6 pb-3 flex items-center gap-2 flex-wrap">
              {strategy.status === 'active' && (
                <ActionButton onClick={() => doAction('pause')} disabled={pending}>
                  <Pause aria-hidden="true" strokeWidth={1.5} className="h-3.5 w-3.5" />
                  Pause
                </ActionButton>
              )}
              {strategy.status === 'paused' && (
                <ActionButton onClick={() => doAction('resume')} disabled={pending}>
                  <Play aria-hidden="true" strokeWidth={1.5} className="h-3.5 w-3.5" />
                  Resume
                </ActionButton>
              )}
              {strategy.status !== 'archived' && (
                <ActionButton onClick={() => doAction('archive')} disabled={pending} intent="danger">
                  <ArchiveIcon aria-hidden="true" strokeWidth={1.5} className="h-3.5 w-3.5" />
                  Archive
                </ActionButton>
              )}
              {strategy.dry_run && (
                <span className="ml-2 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide bg-surface-border/60 text-txt-secondary ring-1 ring-surface-border">
                  DRY-RUN
                </span>
              )}
            </div>
          )}

          <div
            role="tablist"
            aria-label="Detail tabs"
            className="px-6 flex items-center gap-1 border-b border-surface-border"
          >
            <TabButton label="Overview" active={tab === 'overview'} onClick={() => setTab('overview')} />
            <TabButton label="Decisions" active={tab === 'decisions'} onClick={() => setTab('decisions')} />
            {showChatTab && (
              <TabButton label="Persona Chat" active={tab === 'chat'} onClick={() => setTab('chat')} />
            )}
          </div>
        </header>

        <div className="flex-1">
          {error && (
            <p className="px-6 py-4 text-sm text-loss" role="status" aria-live="polite">
              {error}
            </p>
          )}

          {!strategy && !error && (
            <div className="px-6 py-6 space-y-3" aria-busy="true">
              <div className="h-40 rounded bg-surface-border/40 animate-pulse-subtle" />
              <div className="h-24 rounded bg-surface-border/30 animate-pulse-subtle" />
              <div className="h-24 rounded bg-surface-border/20 animate-pulse-subtle" />
            </div>
          )}

          {strategy && tab === 'overview' && (
            <div className="px-6 py-6 space-y-7">
              <div>
                <SubsectionHeader>Equity (30 days)</SubsectionHeader>
                {equityCurve ? (
                  <EquityChart
                    strategies={[{ id: strategy.id, name: strategy.name, curve: equityCurve.strategy }]}
                    benchmarks={equityCurve.benchmarks}
                    range="30d"
                    onRangeChange={() => {}}
                    showRangePicker={false}
                    height="h-56"
                  />
                ) : (
                  <div className="h-56 rounded-lg bg-surface-border/30 animate-pulse-subtle" />
                )}
              </div>

              <div>
                <SubsectionHeader>Open orders</SubsectionHeader>
                <OpenOrdersTable orders={orders} />
              </div>

              <div>
                <SubsectionHeader>Positions</SubsectionHeader>
                <PositionsTable positions={positions} />
              </div>
            </div>
          )}

          {strategy && tab === 'decisions' && (
            <div className="py-2">
              <DecisionsFeed strategyId={strategy.id} />
            </div>
          )}

          {strategy && tab === 'chat' && showChatTab && (
            <PersonaChatTab strategyId={strategy.id} personaKey={strategy.persona_key as string} />
          )}
        </div>
      </aside>
    </div>
  )
}
