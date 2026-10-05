import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router';

import { BarList } from '../../components/charts/BarList';
import { ChartCard } from '../../components/data/ChartCard';
import { QueryState } from '../../components/data/QueryState';
import { formatInteger, formatPercent } from '../../lib/format';
import { PageHeader } from '../../layouts/PageHeader';
import { useCategoryPerformance, useCountryPerformance } from '../analytics/queries';
import { FilterBar } from '../filters/FilterBar';
import { useGlobalFilters } from '../filters/useGlobalFilters';
import { useVideoList } from '../videos/queries';
import { VideoTable } from '../videos/VideoTable';
import { KpiSection } from './KpiSection';
import { VolumeTrendCard } from './VolumeTrendCard';

function ViewAll({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-xs font-medium text-accent-700 hover:underline"
    >
      {label}
      <ArrowRight aria-hidden="true" className="size-3.5" />
    </Link>
  );
}

function withTab(search: string, tab: string): string {
  const params = new URLSearchParams(search);
  params.set('tab', tab);
  return `/analytics?${params.toString()}`;
}

export function OverviewPage() {
  const { filters, search } = useGlobalFilters();
  const categories = useCategoryPerformance(filters);
  const countries = useCountryPerformance(filters);
  const topVideos = useVideoList(filters, { sort: 'views', order: 'desc', page: 1, page_size: 10 });

  return (
    <>
      <PageHeader
        title="Overview"
        description="Trending activity, reach and engagement for the selected period, countries and categories."
      />
      <FilterBar />
      <KpiSection filters={filters} />
      <VolumeTrendCard filters={filters} />

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          title="Category share"
          description="Share of trending volume (snapshots) by each snapshot's category."
          actions={<ViewAll to={withTab(search, 'categories')} label="Category analysis" />}
        >
          <QueryState query={categories} isEmpty={(r) => r.data.length === 0}>
            {({ data }) => (
              <div className="p-4">
                <BarList
                  data={data
                    .slice(0, 8)
                    .map((c) => ({ label: c.category, value: c.volume_share_pct ?? 0 }))}
                  ariaLabel="Bar chart of the top categories by share of trending volume"
                  valueLabel="Share of trending volume"
                  valueFormatter={(v) => formatPercent(v)}
                  axisFormatter={(v) => `${v}%`}
                  labelWidth={136}
                />
              </div>
            )}
          </QueryState>
        </ChartCard>

        <ChartCard
          title="Trending volume by country"
          description="Trending appearances (snapshots) in each country."
          actions={<ViewAll to={withTab(search, 'countries')} label="Country analysis" />}
        >
          <QueryState query={countries} isEmpty={(r) => r.data.length === 0}>
            {({ data }) => (
              <div className="p-4">
                <BarList
                  data={data.map((c) => ({
                    label: c.country_name ?? c.country_code,
                    value: c.trending_volume,
                  }))}
                  ariaLabel="Bar chart of trending volume by country"
                  valueLabel="Trending volume"
                  valueFormatter={formatInteger}
                  labelWidth={112}
                />
              </div>
            )}
          </QueryState>
        </ChartCard>
      </div>

      <ChartCard
        title="Top trending videos"
        description="Highest view counts among videos trending in the selection (latest snapshot within the filters)."
        actions={<ViewAll to={`/trending${search}`} label="All trending videos" />}
      >
        <QueryState
          query={topVideos}
          isEmpty={(r) => r.data.items.length === 0}
          emptyTitle="No trending videos in this selection"
        >
          {({ data }) => (
            <VideoTable
              items={data.items}
              search={search}
              compact
              caption="Top trending videos by views"
            />
          )}
        </QueryState>
      </ChartCard>
    </>
  );
}
