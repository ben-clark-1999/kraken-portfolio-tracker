export type Range = '1W' | '1M' | '3M' | '6M' | '1Y' | 'ALL'

export const RANGE_DAYS: Record<Range, number | null> = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '1Y': 365,
  ALL: null,
}

const ORDER: Range[] = ['1W', '1M', '3M', '6M', '1Y', 'ALL']

interface Props {
  value: Range
  onChange: (next: Range) => void
}

export default function RangePicker({ value, onChange }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Time range"
      className="inline-flex items-center gap-px rounded-md border border-surface-border bg-surface p-0.5"
    >
      {ORDER.map(r => {
        const active = r === value
        return (
          <button
            key={r}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(r)}
            className={
              `px-2.5 py-1 rounded text-xs font-medium tracking-wide transition-colors ` +
              (active
                ? 'bg-kraken/20 text-txt-primary'
                : 'text-txt-secondary hover:text-txt-primary hover:bg-surface-hover')
            }
          >
            {r}
          </button>
        )
      })}
    </div>
  )
}
