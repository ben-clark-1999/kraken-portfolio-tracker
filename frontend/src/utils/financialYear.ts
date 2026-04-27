/**
 * Australian financial year helper. Mirrors backend/utils/financial_year.py.
 * AU FY runs July 1 → June 30. Returns 'YYYY-YY' (e.g. '2025-26').
 */
export function financialYearFrom(d: Date): string {
  const month = d.getMonth() + 1 // JS months are 0-indexed
  const year = d.getFullYear()
  const start = month >= 7 ? year : year - 1
  const endShort = (start + 1) % 100
  return `${start}-${endShort.toString().padStart(2, '0')}`
}

/**
 * Returns the FY for "today" in the user's local timezone.
 * Useful for default-select on add-entry forms.
 */
export function currentFinancialYear(): string {
  return financialYearFrom(new Date())
}
