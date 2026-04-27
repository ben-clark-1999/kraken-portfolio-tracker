/**
 * Single source of truth for asset display colors.
 * Adding a new asset = add one entry here.
 */

const COLORS: Record<string, string> = {
  ETH: '#627EEA',
  SOL: '#9945FF',
  ADA: '#06B6D4',
  LINK: '#F59E0B',
}

const FALLBACK = '#5f5a70'

export function getAssetColor(asset: string): string {
  return COLORS[asset] ?? FALLBACK
}
