import { useState } from 'react';

import type { ChannelPerformance, ChannelSort, FilterParams } from '../../api/types';
import { BarList } from '../../components/charts/BarList';
import { ChartCard } from '../../components/data/ChartCard';
import { DataTable, type Column } from '../../components/data/DataTable';
import { QueryState } from '../../components/data/QueryState';
import { Select } from '../../components/ui/Select';
import { formatCompact, formatInteger, formatRate } from '../../lib/format';
import { useTopChannels } from './queries';

/** Labels for every backend channel sort key (typed against the generated union). */
const SORT_LABELS: Record<ChannelSort, string> = {
  unique_videos: 'Unique videos',
  trending_volume: 'Trending volume',
  views: 'Views',
};
const SORT_OPTIONS = (Object.keys(SORT_LABELS) as ChannelSort[]).map((value) => ({
  value,
  label: SORT_LABELS[value],
}));
const LIMITS = [
  { value: '10', label: '10' },
  { value: '25', label: '25' },
  { value: '50', label: '50' },
] as const;

const columns: Column<ChannelPerformance>[] = [
  {
    key: 'channel',
    header: 'Channel',
    cell: (c) => (
      <span className="font-medium text-slate-900">{c.channel_title ?? c.channel_id}</span>
    ),
  },
  {
    key: 'subscribers',
    header: 'Subscribers',
    align: 'right',
    cell: (c) => <span title={formatInteger(c.subscribers)}>{formatCompact(c.subscribers)}</span>,
  },
  {
    key: 'videos',
    header: 'Unique videos',
    align: 'right',
    cell: (c) => formatInteger(c.unique_videos),
  },
  {
    key: 'volume',
    header: 'Trending volume',
    align: 'right',
    cell: (c) => formatInteger(c.trending_volume),
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

export function ChannelsPanel({ filters }: { filters: FilterParams }) {
  const [sort, setSort] = useState<ChannelSort>('unique_videos');
  const [limit, setLimit] = useState<'10' | '25' | '50'>('10');
  const channels = useTopChannels(filters, { sort, limit: Number(limit) });

  return (
    <ChartCard
      title="Top channels"
      description="Title and subscribers come from each channel's most recent snapshot within the filters."
      actions={
        <>
          <Select
            label="Rank by"
            showLabel
            value={sort}
            options={SORT_OPTIONS}
            onChange={setSort}
          />
          <Select label="Show" showLabel value={limit} options={LIMITS} onChange={setLimit} />
        </>
      }
    >
      <QueryState query={channels} isEmpty={(r) => r.data.length === 0}>
        {({ data }) => (
          <>
            <div className="border-b border-slate-100 p-4">
              <BarList
                data={data
                  .slice(0, 10)
                  .map((c) => ({ label: c.channel_title ?? c.channel_id, value: c[sort] }))}
                ariaLabel={`Bar chart of the top channels by ${SORT_LABELS[sort].toLowerCase()}`}
                valueLabel={SORT_LABELS[sort]}
                valueFormatter={sort === 'views' ? formatCompact : formatInteger}
                labelWidth={160}
              />
            </div>
            <DataTable
              columns={columns}
              rows={data}
              rowKey={(c) => c.channel_id}
              caption="Top channels"
            />
          </>
        )}
      </QueryState>
    </ChartCard>
  );
}
