export interface AssetPosition {
  asset: string
  quantity: number
  price_aud: number
  value_aud: number
  cost_basis_aud: number
  unrealised_pnl_aud: number
  allocation_pct: number
}

export interface PortfolioSummary {
  total_value_aud: number
  positions: AssetPosition[]
  captured_at: string
  next_dca_date: string | null
}

export interface SnapshotAsset {
  quantity: number
  value_aud: number
  price_aud: number
}

export interface PortfolioSnapshot {
  id: string
  captured_at: string
  total_value_aud: number
  assets: Record<string, SnapshotAsset>
}

export interface DCAEntry {
  lot_id: string
  asset: string
  acquired_at: string
  quantity: number
  cost_aud: number
  cost_per_unit_aud: number
  current_price_aud: number
  current_value_aud: number
  unrealised_pnl_aud: number
}
