import { Loader2 } from 'lucide-react'
import type { ToolActivity } from '../types/agent'

const TOOL_LABELS: Record<string, string> = {
  get_portfolio_summary: 'Looking up your portfolio balance',
  get_dca_history: 'Checking your purchase history',
  get_recent_snapshots: 'Reading recent portfolio history',
  get_up_balance: 'Checking your Up Bank balance',
  get_up_spending_by_category: 'Looking at your spending breakdown',
  get_up_cashflow: 'Calculating cash flow',
  get_up_recent_transactions: 'Reading recent transactions',
  get_combined_net_worth: 'Calculating your net worth',
  get_recurring_charges: 'Listing recurring charges',
  get_my_paper_state: 'Reading your paper-trading state',
  get_my_recent_decisions: 'Looking at recent strategy decisions',
  get_market_snapshot: 'Getting a market snapshot',
  place_paper_order: 'Placing a paper order',
  cancel_paper_order: 'Cancelling the paper order',
}

function labelFor(name: string): string {
  if (TOOL_LABELS[name]) return TOOL_LABELS[name]
  // Fallback: snake_case → Sentence case
  const cleaned = name.replace(/^get_/, '').replace(/_/g, ' ').trim()
  if (!cleaned) return 'Working…'
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1) + '…'
}

interface Props {
  activity: ToolActivity
}

export default function AgentToolStatus({ activity }: Props) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-txt-muted">
      <Loader2 className="w-3.5 h-3.5 animate-spin text-kraken/70" aria-hidden />
      <span>{labelFor(activity.tool)}</span>
    </span>
  )
}
