export interface UpAccount {
  id: string
  display_name: string
  account_type: 'TRANSACTIONAL' | 'SAVER' | 'HOME_LOAN'
  ownership_type: 'INDIVIDUAL' | 'JOINT'
  balance_value: number
  balance_currency: string
  created_at: string
}

export interface UpTransaction {
  id: string
  account_id: string
  status: 'HELD' | 'SETTLED'
  description: string
  message: string | null
  raw_text: string | null
  amount_value: number
  amount_currency: string
  category_id: string | null
  parent_category_id: string | null
  created_at: string
  settled_at: string | null
}

export interface CashflowRow {
  period: string
  income: number
  expense: number
}

export interface SyncStatus {
  state: 'ready' | 'syncing' | 'error'
  last_synced_at: string | null
  error: string | null
}

export interface CombinedSnapshot {
  captured_at: string
  /** Most-recent-known crypto value at this bucket; null only if no
   *  crypto snapshot has occurred yet at or before this bucket. */
  crypto: number | null
  /** Most-recent-known UP value at this bucket; null only if no UP
   *  snapshot has occurred yet at or before this bucket. */
  up: number | null
  /** crypto + up; null if either is null. */
  total: number | null
}

export interface CombinedSummary {
  crypto: number
  up: number
  total: number
}

export type RecurringCadence = 'weekly' | 'fortnightly' | 'monthly' | 'yearly'

export interface RecurringCharge {
  name: string
  sample_description: string
  cadence: RecurringCadence
  median_amount: number
  last_charged_at: string
  next_expected_at: string
  occurrence_count: number
  monthly_equivalent: number
}
