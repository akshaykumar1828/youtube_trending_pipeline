import type { CategoryPerformance, FilterParams } from '../../api/types';
import { BarList } from '../../components/charts/BarList';
import { seriesColor } from '../../components/charts/chartTheme';
import { pivotByDate } from '../../components/charts/pivot';
import { TimeSeriesChart } from '../../components/charts/TimeSeriesChart';
import { ChartCard } from '../../components/data/ChartCard';
import { DataTable, type Column } from '../../components/data/DataTable';
import { QueryState } from '../../components/data/QueryState';
import { LoadingState } from '../../components/data/states';
import { formatCompact, formatInteger, formatPercent, formatRate } from '../../lib/format';
import { useDailyVolume } from '../overview/queries';
import { useCategoryPerformance } from './queries';

const TREND_CATEGORIES = 6;

const columns: Column<CategoryPerformance>[] = [
  {
    key: 'category',
    header: 'Category',
    cell: (c) => <span className="font-medium text-slate-900">{c.category}</span>,
  },
  {
    key: 'volume',
    header: 'Trending volume',
    align: 'right',
    cell: (c) => formatInteger(c.trending_volume),
  },
  {
    key: 'share',
    header: 'Share of volume',
    align: 'right',
    cell: (c) => formatPercent(c.volume_share_pct),
  },
  {
    key: 'videos',
    header: 'Unique videos',
    align: 'right',
    cell: (c) => formatInteger(c.unique_videos),
  },
  {
    key: 'views',
    header: 'Views',
    align: 'right',
    cell: (c) => <span title={formatInteger(c.views)}>{formatCompact(c.views)}</span>,
  },
  {
    key: 'engagement',
    header: 'Engagement rate',
    align: 'right',
    cell: (c) => formatRate(c.engagement_rate),
  },
];

export function CategoriesPanel({ filters }: { filters: FilterParams }) {
  const categories = useCategoryPerformance(filters);
  const trend = useDailyVolume(filters, { split_by: 'category' });
  const ranked = categories.data?.data.map((c) => c.category).slice(0, TREND_CATEGORIES) ?? [];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          title="Share of trending volume"
          description="Snapshot-level: each snapshot counts toward its own category."
        >
          <QueryState query={categories} isEmpty={(r) => r.data.length === 0}>
            {({ data }) => (
              <div className="p-4">
                <BarList
                  data={data.map((c) => ({ label: c.category, value: c.volume_share_pct ?? 0 }))}
                  ariaLabel="Bar chart of categories by share of trending volume"
                  valueLabel="Share of trending volume"
                  valueFormatter={(v) => formatPercent(v)}
                  axisFormatter={(v) => `${v}%`}
                  labelWidth={140}
                />
              </div>
            )}
          </QueryState>
        </ChartCard>

        <ChartCard
          title={`Daily volume, top ${TREND_CATEGORIES} categories`}
          description="Categories ranked by trending volume in the selection."
        >
          <QueryState
            query={trend}
            loading={<LoadingState rows={6} label="Loading category trend" />}
            isEmpty={(r) => r.data.series.length === 0}
          >
            {({ data }) => {
              const series = ranked
                .map((key) => data.series.find((s) => s.key === key))
                .filter((s) => s !== undefined)
                .map((s, i) => ({ key: s.key ?? `series-${i}`, points: s.points }));
              return (
                <div className="p-4">
                  <TimeSeriesChart
                    data={pivotByDate(series, (p) => p.trending_volume)}
                    series={series.map((s, i) => ({
                      key: s.key,
                      label: s.key,
                      color: seriesColor(i),
                    }))}
                    ariaLabel="Line chart of daily trending volume for the top categories"
                    height={300}
                  />
                </div>
              );
            }}
          </QueryState>
        </ChartCard>
      </div>

      <ChartCard
        title="Category performance"
        description="Video-level metrics use each video's latest snapshot within the filters; views are counted once per video."
      >
        <QueryState query={categories} isEmpty={(r) => r.data.length === 0}>
          {({ data }) => (
            <DataTable
              columns={columns}
              rows={data}
              rowKey={(c) => c.category}
              caption="Category performance"
            />
          )}
        </QueryState>
      </ChartCard>
    </div>
  );
}
