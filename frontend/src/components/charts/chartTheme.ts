/** Shared Recharts styling: one accent colour, muted series palette, quiet axes and grid. */

export const ACCENT = '#dc2626'; // red-600 (matches --color-accent-600)
export const SECONDARY = '#94a3b8'; // slate-400

/** Used only where several series must be distinguished (e.g. countries). */
export const SERIES_COLORS = [
  '#dc2626',
  '#0d9488',
  '#d97706',
  '#7c3aed',
  '#db2777',
  '#0891b2',
  '#65a30d',
  '#2563eb',
  '#475569',
] as const;

export function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length] ?? ACCENT;
}

export const axisProps = {
  stroke: '#94a3b8',
  tick: { fill: '#64748b', fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

export const gridProps = {
  stroke: '#e2e8f0',
  strokeDasharray: '3 3',
  vertical: false,
} as const;

export const tooltipProps = {
  contentStyle: {
    border: '1px solid #e2e8f0',
    borderRadius: 6,
    boxShadow: 'none',
    fontSize: 12,
    padding: '6px 10px',
  },
  labelStyle: { color: '#0f172a', fontWeight: 600, marginBottom: 2 },
  itemStyle: { padding: 0 },
  cursor: { fill: '#f1f5f9', stroke: '#cbd5e1' },
} as const;
