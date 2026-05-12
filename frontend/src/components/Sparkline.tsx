import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface Props {
  values: number[]
  color: string
  height?: number
}

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
        <LineChart data={data} margin={{ top: 1, right: 1, bottom: 1, left: 1 }}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            strokeLinecap="round"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
