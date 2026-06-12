/**
 * Currency display for hero numbers: integer dollars at full size,
 * cents stepped down and muted so the eye lands on what matters.
 * Sizes are em-relative — the parent's text size and color set the scale.
 */
interface Props {
  value: number
  className?: string
}

export default function Money({ value, className }: Props) {
  const sign = value < 0 ? '−' : ''
  const formatted = Math.abs(value).toLocaleString('en-AU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  const [whole, cents] = formatted.split('.')
  return (
    <span className={className}>
      {sign}${whole}
      <span className="text-[0.52em] font-medium text-txt-secondary">.{cents}</span>
    </span>
  )
}
