import { useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { EngagementAnalysis, FilterParams } from '../../api/types';
import { ACCENT, axisProps, gridProps, tooltipProps } from '../../components/charts/chartTheme';
import { ChartCard } from '../../components/data/ChartCard';
import { DataTable, type Column } from '../../components/data/DataTable';
import { QueryState } from '../../components/data/QueryState';
import { StatTile } from '../../components/data/StatTile';
import { Select } from '../../components/ui/Select';
import { formatCompact, formatInteger, formatRate } from '../../lib/format';
import { useEngagementAnalysis } from './queries';

type CategoryRow = EngagementAnalysis['by_category'][number];
type ScatterRow = EngagementAnalysis['scatter'][number];

const SCATTER_LIMITS = [
  { value: '100', label: '100' },
  { value: '200', label: '200' },
  { value: '500', label: '500' },
] as const;

function bucketLabel(lower: number, upper: number | null): string {
  return upper == null ? `≥${lower}%` : `${lower}–${upper}%`;
}

function SpreadBar({ row, max }: { row: CategoryRow; max: number }) {
  if (row.p25 == null || row.p75 == null || max <= 0) return null;
  const left = (row.p25 / max) * 100;
  const width = Math.max(((row.p75 - row.p25) / max) * 100, 0.5);
  const median = row.p50 == null ? null : (row.p50 / max) * 100;
  return (
    <div aria-hidden="true" className="relative h-2 w-40 rounded-sm bg-slate-100">
      <div
        className="absolute inset-y-0 rounded-sm bg-accent-200"
        style={{ left: `${left}%`, width: `${width}%` }}
      />
      {median != null && (
        <div
          className="absolute inset-y-[-2px] w-0.5 bg-accent-700"
          style={{ left: `${median}%` }}
        />
      )}
    </div>
  );
}

function ScatterTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: ScatterRow }[];
}) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return (
    <div className="max-w-xs rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs">
      <p className="font-medium text-slate-900">{row.title ?? row.video_id}</p>
      <p className="text-slate-600">
        {formatInteger(row.views)} views · {formatRate(row.engagement_rate)} · {row.category}
      </p>
    </div>
  );
}

export function EngagementPanel({ filters }: { filters: FilterParams }) {
  const [scatterLimit, setScatterLimit] = useState<'100' | '200' | '500'>('200');
  const engagement = useEngagementAnalysis(filters, { scatter_limit: Number(scatterLimit) });

  return (
    <QueryState query={engagement} isEmpty={(r) => r.data.totals.videos === 0}>
      {({ data }) => {
        const { totals, distribution } = data;
        const maxP75 = Math.max(0, ...data.by_category.map((c) => c.p75 ?? 0));
        const categoryColumns: Column<CategoryRow>[] = [
          {
            key: 'category',
            header: 'Category',
            cell: (c) => <span className="font-medium text-slate-900">{c.category}</span>,
          },
          { key: 'videos', header: 'Videos', align: 'right', cell: (c) => formatInteger(c.videos) },
          { key: 'p25', header: '25th pct', align: 'right', cell: (c) => formatRate(c.p25) },
          { key: 'p50', header: 'Median', align: 'right', cell: (c) => formatRate(c.p50) },
          { key: 'p75', header: '75th pct', align: 'right', cell: (c) => formatRate(c.p75) },
          {
            key: 'spread',
            header: 'Spread (25th–75th, median)',
            cell: (c) => <SpreadBar row={c} max={maxP75} />,
            className: 'hidden md:table-cell',
          },
        ];
        return (
          <div className="space-y-4">
            <ChartCard
              title="Engagement totals"
              description="Video-level, from each video's latest snapshot within the filters. Hidden like counts are stored as 0."
            >
              <dl className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 xl:grid-cols-6">
                <StatTile label="Videos" value={formatInteger(totals.videos)} />
                <StatTile
                  label="Without views (excluded)"
                  value={formatInteger(totals.videos_without_views)}
                />
                <StatTile
                  label="Views"
                  value={formatCompact(totals.views)}
                  hint={formatInteger(totals.views)}
                />
                <StatTile
                  label="Likes"
                  value={formatCompact(totals.likes)}
                  hint={formatInteger(totals.likes)}
                />
                <StatTile
                  label="Comments"
                  value={formatCompact(totals.comments)}
                  hint={formatInteger(totals.comments)}
                />
                <StatTile label="Engagement rate" value={formatRate(totals.engagement_rate)} />
              </dl>
            </ChartCard>

            <div className="grid gap-4 xl:grid-cols-2">
              <ChartCard
                title="Distribution of per-video engagement"
                description={`Percentiles — 25th ${formatRate(distribution.p25)} · median ${formatRate(distribution.p50)} · 75th ${formatRate(distribution.p75)} · 90th ${formatRate(distribution.p90)}`}
              >
                <figure
                  role="img"
                  aria-label="Histogram of videos by engagement rate bucket"
                  className="m-0 p-4"
                >
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart
                      data={data.histogram.map((b) => ({
                        label: bucketLabel(b.lower_pct, b.upper_pct),
                        videos: b.videos,
                      }))}
                      margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                    >
                      <CartesianGrid {...gridProps} />
                      <XAxis
                        dataKey="label"
                        {...axisProps}
                        interval={0}
                        angle={-30}
                        textAnchor="end"
                        height={48}
                      />
                      <YAxis
                        {...axisProps}
                        width={48}
                        tickFormatter={(v: number) => formatCompact(v)}
                      />
                      <Tooltip
                        {...tooltipProps}
                        formatter={(v) => [formatInteger(Number(v)), 'Videos']}
                      />
                      <Bar
                        dataKey="videos"
                        name="Videos"
                        fill={ACCENT}
                        isAnimationActive={false}
                        radius={[2, 2, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </figure>
              </ChartCard>

              <ChartCard
                title="Views vs engagement"
                description="Top videos by views (log scale)."
                actions={
                  <Select
                    label="Videos shown"
                    showLabel
                    value={scatterLimit}
                    options={SCATTER_LIMITS}
                    onChange={setScatterLimit}
                  />
                }
              >
                <figure
                  role="img"
                  aria-label="Scatter plot of views against engagement rate for the top videos"
                  className="m-0 p-4"
                >
                  <ResponsiveContainer width="100%" height={260}>
                    <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis
                        type="number"
                        dataKey="views"
                        name="Views"
                        scale="log"
                        domain={['auto', 'auto']}
                        {...axisProps}
                        tickFormatter={(v: number) => formatCompact(v)}
                      />
                      <YAxis
                        type="number"
                        dataKey="engagement_rate"
                        name="Engagement rate"
                        {...axisProps}
                        width={48}
                        tickFormatter={(v: number) => formatRate(v, 0)}
                      />
                      <Tooltip content={<ScatterTooltip />} cursor={{ strokeDasharray: '3 3' }} />
                      <Scatter
                        data={data.scatter.filter((s) => (s.views ?? 0) > 0)}
                        fill={ACCENT}
                        fillOpacity={0.55}
                        isAnimationActive={false}
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                </figure>
              </ChartCard>
            </div>

            <ChartCard
              title="Engagement by category"
              description="Per-video engagement percentiles (videos with views), grouped by the latest snapshot's category."
            >
              <DataTable
                columns={categoryColumns}
                rows={data.by_category}
                rowKey={(c) => c.category}
                caption="Engagement percentiles by category"
              />
            </ChartCard>
          </div>
        );
      }}
    </QueryState>
  );
}
