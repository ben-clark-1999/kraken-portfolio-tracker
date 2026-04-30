/**
 * Single source of truth for per-asset chart/sparkline/segment colours.
 *
 * Returns the hex value (not a Tailwind class) because Recharts' stroke/fill
 * props need raw colours. For Tailwind contexts (bg-asset-eth etc.), use the
 * tokens directly — the values here mirror the tailwind.config.js asset block.
 */

const ASSET_COLORS: Record<string, string> = {
  ETH: '#5EEAD4',  // accent teal — flagship
  SOL: '#7B61FF',  // kraken violet
  ADA: '#60A5FA',  // blue
  LINK: '#22D3EE', // teal-2 (cyan)
}

const FALLBACK = '#5f5a70' // txt-muted — neutral grey for unknown assets

export function colorForAsset(asset: string): string {
  return ASSET_COLORS[asset] ?? FALLBACK
}

export function knownAssets(): string[] {
  return Object.keys(ASSET_COLORS)
}
