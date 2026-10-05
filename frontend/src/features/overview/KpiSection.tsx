import type { FilterParams } from '../../api/types';
import { MetricCard, MetricCardSkeleton } from '../../components/data/MetricCard';
import { QueryState } from '../../components/data/QueryState';
import {
  formatChangePct,
  formatChangePts,
  formatCompact,
  formatDate,
  formatInteger,
  formatRate,
} from '../../lib/format';
import { useKpis } from './queries';

function KpiSkeletons() {
  return (
    <div role="status" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      <span className="sr-only">Loading key metrics…</span>
      {Array.from({ length: 5 }, (_, i) => (
        <MetricCardSkeleton key={i} />
      ))}
    </div>
  );
}

/** The five KPIs returned by /api/v1/overview/kpis, with the backend's change definitions. */
export function KpiSection({ filters }: { filters: FilterParams }) {
  const kpis = useKpis(filters);
  return (
    <section aria-labelledby="kpi-heading" className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="kpi-heading" className="text-sm font-semibold text-slate-900">
          Key metrics
        </h2>
        {kpis.data && (
          <p className="text-xs text-slate-500">
            {formatDate(kpis.data.filters.start_date)} – {formatDate(kpis.data.filters.end_date)} ·{' '}
            {kpis.data.filters.days} days
          </p>
        )}
      </div>
      <QueryState
        query={kpis}
        loading={<KpiSkeletons />}
        className="rounded-lg border border-slate-200 bg-white"
        isEmpty={(r) => r.data.unique_videos.value === 0}
        emptyTitle="No trending videos in this selection"
      >
        {({ data: k }) => {
          const comparison = `vs previous ${k.period.days} days`;
          const noComparison = k.previous_period.available
            ? 'No change available'
            : 'No earlier period in the data';
          return (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              <MetricCard
                label="Trending volume"
                value={formatInteger(k.trending_volume.value)}
                change={formatChangePct(k.trending_volume.change_pct)}
                changeValue={k.trending_volume.change_pct}
                comparisonLabel={comparison}
                noComparisonText={noComparison}
                definition="Snapshot-level: trending appearances (country × video × day) in the selection."
              />
              <MetricCard
                label="Unique videos"
                value={formatInteger(k.unique_videos.value)}
                change={formatChangePct(k.unique_videos.change_pct)}
                changeValue={k.unique_videos.change_pct}
                comparisonLabel={comparison}
                noComparisonText={noComparison}
                definition="Video-level: distinct videos that trended in the selection."
              />
              <MetricCard
                label="Views"
                value={formatCompact(k.views.value)}
                change={formatChangePct(k.views.change_pct)}
                changeValue={k.views.change_pct}
                comparisonLabel={comparison}
                noComparisonText={noComparison}
                definition="Lifetime views from each video's latest snapshot within the filters, counted once per video (never summed across snapshots)."
              />
              <MetricCard
                label="Engagement rate"
                value={formatRate(k.engagement_rate.value)}
                change={formatChangePts(k.engagement_rate.change_pts)}
                changeValue={k.engagement_rate.change_pts}
                comparisonLabel={comparison}
                noComparisonText={noComparison}
                definition="(Likes + comments) / views over the same latest snapshots. Change in percentage points."
              />
              <MetricCard
                label="Unique channels"
                value={formatInteger(k.unique_channels.value)}
                change={formatChangePct(k.unique_channels.change_pct)}
                changeValue={k.unique_channels.change_pct}
                comparisonLabel={comparison}
                noComparisonText={noComparison}
                definition="Distinct channels with at least one trending appearance in the selection."
              />
            </div>
          );
        }}
      </QueryState>
    </section>
  );
}
