import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { formatCompact, formatDate, formatInteger, formatShortDate } from '../../lib/format';
import { axisProps, gridProps, tooltipProps } from './chartTheme';

export interface Series {
  key: string;
  label: string;
  color: string;
}

interface TimeSeriesChartProps {
  /** One row per date: { date: 'YYYY-MM-DD', [series.key]: number }. */
  data: Record<string, string | number | null>[];
  series: Series[];
  ariaLabel: string;
  height?: number;
  valueFormatter?: (value: number) => string;
  showLegend?: boolean;
}

export function TimeSeriesChart({
  data,
  series,
  ariaLabel,
  height = 260,
  valueFormatter = formatInteger,
  showLegend = series.length > 1,
}: TimeSeriesChartProps) {
  return (
    <figure role="img" aria-label={ariaLabel} className="m-0">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis
            dataKey="date"
            {...axisProps}
            tickFormatter={(value: string) => formatShortDate(value)}
            minTickGap={24}
          />
          <YAxis
            {...axisProps}
            width={48}
            tickFormatter={(value: number) => formatCompact(value)}
          />
          <Tooltip
            {...tooltipProps}
            labelFormatter={(label) => formatDate(String(label))}
            formatter={(value) =>
              typeof value === 'number' ? valueFormatter(value) : String(value)
            }
          />
          {showLegend && <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />}
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}
