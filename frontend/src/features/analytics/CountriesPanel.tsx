import { Info } from 'lucide-react';

import type { CountryPerformance, FilterParams } from '../../api/types';
import { BarList } from '../../components/charts/BarList';
import { SECONDARY } from '../../components/charts/chartTheme';
import { ChartCard } from '../../components/data/ChartCard';
import { DataTable, type Column } from '../../components/data/DataTable';
import { QueryState } from '../../components/data/QueryState';
import { formatCompact, formatInteger, formatRate } from '../../lib/format';
import { useCountryPerformance } from './queries';

const columns: Column<CountryPerformance>[] = [
  {
    key: 'country',
    header: 'Country',
    cell: (c) => (
      <span className="font-medium text-slate-900">
        {c.country_name ?? c.country_code}{' '}
        <span className="font-mono text-xs font-normal text-slate-500">{c.country_code}</span>
      </span>
    ),
  },
  {
    key: 'volume',
    header: 'Trending volume',
    align: 'right',
    cell: (c) => formatInteger(c.trending_volume),
  },
  {
    key: 'videos',
    header: 'Unique videos',
    align: 'right',
    cell: (c) => formatInteger(c.unique_videos),
  },
  {
    key: 'views',
    header: 'Views of trending videos',
    align: 'right',
    cell: (c) => (
      <span title={formatInteger(c.views_of_trending_videos)}>
        {formatCompact(c.views_of_trending_videos)}
      </span>
    ),
  },
  {
    key: 'engagement',
    header: 'Engagement rate',
    align: 'right',
    cell: (c) => formatRate(c.engagement_rate),
  },
];

export function CountriesPanel({ filters }: { filters: FilterParams }) {
  const countries = useCountryPerformance(filters);
  const label = (c: CountryPerformance) => c.country_name ?? c.country_code;

  return (
    <div className="space-y-4">
      <p className="flex items-start gap-2 rounded-md border border-slate-200 bg-white px-3 py-2.5 text-xs text-slate-600">
        <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-accent-600" />
        <span>
          Country metrics use each video’s latest snapshot within the filters{' '}
          <em>in that country</em>. “Views of trending videos” are global lifetime views of videos
          that trended there — not views from that country — so they do not add up across countries.
        </span>
      </p>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard
          title="Trending volume by country"
          description="Trending appearances (snapshots) per country."
        >
          <QueryState query={countries} isEmpty={(r) => r.data.length === 0}>
            {({ data }) => (
              <div className="p-4">
                <BarList
                  data={data.map((c) => ({ label: label(c), value: c.trending_volume }))}
                  ariaLabel="Bar chart of trending volume by country"
                  valueLabel="Trending volume"
                  valueFormatter={formatInteger}
                  labelWidth={112}
                />
              </div>
            )}
          </QueryState>
        </ChartCard>
        <ChartCard
          title="Engagement rate by country"
          description="(Likes + comments) / views of the country's trending videos."
        >
          <QueryState query={countries} isEmpty={(r) => r.data.length === 0}>
            {({ data }) => (
              <div className="p-4">
                <BarList
                  data={data.map((c) => ({ label: label(c), value: c.engagement_rate ?? 0 }))}
                  ariaLabel="Bar chart of engagement rate by country"
                  valueLabel="Engagement rate"
                  valueFormatter={(v) => formatRate(v)}
                  axisFormatter={(v) => formatRate(v, 1)}
                  labelWidth={112}
                  color={SECONDARY}
                />
              </div>
            )}
          </QueryState>
        </ChartCard>
      </div>
      <ChartCard title="Country performance">
        <QueryState query={countries} isEmpty={(r) => r.data.length === 0}>
          {({ data }) => (
            <DataTable
              columns={columns}
              rows={data}
              rowKey={(c) => c.country_code}
              caption="Country performance"
            />
          )}
        </QueryState>
      </ChartCard>
    </div>
  );
}
