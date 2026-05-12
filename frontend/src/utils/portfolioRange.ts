import type { PortfolioSnapshot } from '../types'

export function unionAssetKeys(snapshots: PortfolioSnapshot[]): string[] {
  const set = new Set<string>()
  for (const s of snapshots) {
    for (const k of Object.keys(s.assets)) {
      set.add(k)
    }
  }
  return Array.from(set)
}

export function computeRangeDelta(snapshots: PortfolioSnapshot[]): number | null {
  if (snapshots.length < 2) return null
  const start = snapshots[0].total_value_aud
  const end = snapshots[snapshots.length - 1].total_value_aud
  if (start === 0) return null
  return ((end - start) / start) * 100
}
