import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface Props {
  /** Series of values to plot. Order = chronological. */
  values: number[]
  /** Hex stroke colour. */
  color: string
  /** Container height in px. Default 28. */
  height?: number
}

/**
 * Inline trendline for an asset row. No axes, tooltip, labels, or fill —
 * the precise value sits next to it, so this only carries shape.
 * Renders a flat line for length-1 series and an empty box for length-0.
 */
export default function Sparkline({ values, color, height = 28 }: Props) {
  if (values.length === 0) {
    return <div style={{ height }} className="w-full" aria-hidden="true" />
  }

  const data = (values.length === 1 ? [values[0], values[0]] : values).map((v, i) => ({
    i,
    v,
  }))

  return (
    <div style={{ height }} className="w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 1, right: 2, bottom: 1, left: 2 }}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
