import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { ACCENT, axisProps, gridProps, tooltipProps } from './chartTheme';

export interface BarDatum {
  label: string;
  value: number;
}

interface BarListProps {
  data: BarDatum[];
  ariaLabel: string;
  valueLabel: string;
  valueFormatter: (value: number) => string;
  axisFormatter?: (value: number) => string;
  labelWidth?: number;
  color?: string;
}

/** Horizontal bar chart for ranked categories/countries/channels. */
export function BarList({
  data,
  ariaLabel,
  valueLabel,
  valueFormatter,
  axisFormatter = valueFormatter,
  labelWidth = 120,
  color = ACCENT,
}: BarListProps) {
  const height = Math.max(120, data.length * 30 + 32);
  return (
    <figure role="img" aria-label={ariaLabel} className="m-0">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid {...gridProps} vertical horizontal={false} />
          <XAxis type="number" {...axisProps} tickFormatter={axisFormatter} />
          <YAxis
            type="category"
            dataKey="label"
            {...axisProps}
            width={labelWidth}
            interval={0}
            tick={{ ...axisProps.tick, fill: '#334155' }}
          />
          <Tooltip
            {...tooltipProps}
            formatter={(value) => [
              typeof value === 'number' ? valueFormatter(value) : String(value),
              valueLabel,
            ]}
          />
          <Bar
            dataKey="value"
            name={valueLabel}
            fill={color}
            barSize={14}
            radius={[0, 2, 2, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
