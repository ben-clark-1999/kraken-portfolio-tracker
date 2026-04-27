export type TaxEntryKind = 'deductible' | 'income' | 'tax_paid'

export type DeductibleType =
  | 'software' | 'hardware'
  | 'professional_development' | 'professional_services'
  | 'crypto_related' | 'other'

export type IncomeType = 'salary_wages' | 'freelance' | 'interest' | 'dividends' | 'other'
export type TaxPaidType = 'payg_withholding' | 'payg_installment' | 'bas_payment' | 'other'

export interface TaxAttachment {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  uploaded_at: string
}

export interface TaxEntry {
  id: string
  description: string
  amount_aud: number
  date: string
  type: string
  notes: string | null
  financial_year: string
  attachments: TaxAttachment[]
  created_at: string
  updated_at: string
}

export interface TaxEntryCreate {
  description: string
  amount_aud: number
  date: string
  type: string
  notes?: string | null
  attachment_ids?: string[]
}

export interface TaxEntryUpdate {
  description?: string
  amount_aud?: number
  date?: string
  type?: string
  notes?: string | null
}

export interface KrakenAssetActivity {
  aud_spent: number
  buy_count: number
  current_value_aud: number
}

export interface KrakenFYActivity {
  total_aud_invested: number
  total_buys: number
  per_asset: Record<string, KrakenAssetActivity>
}

export interface FYOverview {
  financial_year: string
  income_total_aud: number
  tax_paid_total_aud: number
  deductibles_total_aud: number
  kraken_activity: KrakenFYActivity
}

export const KIND_TO_PATH: Record<TaxEntryKind, string> = {
  deductible: 'deductibles',
  income: 'income',
  tax_paid: 'paid',
}

export const DEDUCTIBLE_TYPES: DeductibleType[] = [
  'software',
  'hardware',
  'professional_development',
  'professional_services',
  'crypto_related',
  'other',
]

export const INCOME_TYPES: IncomeType[] = [
  'salary_wages',
  'freelance',
  'interest',
  'dividends',
  'other',
]

export const TAX_PAID_TYPES: TaxPaidType[] = [
  'payg_withholding',
  'payg_installment',
  'bas_payment',
  'other',
]

export const TYPE_LABELS: Record<string, string> = {
  // deductible
  software: 'Software & subscriptions',
  hardware: 'Hardware & equipment',
  professional_development: 'Professional development',
  professional_services: 'Professional services',
  crypto_related: 'Crypto-related',
  other: 'Other',
  // income
  salary_wages: 'Salary / wages',
  freelance: 'Freelance',
  interest: 'Interest',
  dividends: 'Dividends',
  // tax_paid
  payg_withholding: 'PAYG withholding',
  payg_installment: 'PAYG installment',
  bas_payment: 'BAS payment',
}
