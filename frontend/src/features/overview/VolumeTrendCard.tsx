import { useState } from 'react';

import type { FilterParams } from '../../api/types';
import { ACCENT, SECONDARY, seriesColor } from '../../components/charts/chartTheme';
import { pivotByDate } from '../../components/charts/pivot';
import { TimeSeriesChart } from '../../components/charts/TimeSeriesChart';
import { ChartCard } from '../../components/data/ChartCard';
import { QueryState } from '../../components/data/QueryState';
import { LoadingState } from '../../components/data/states';
import { SegmentedControl } from '../../components/ui/SegmentedControl';
import { useDailyVolume } from './queries';

type Split = 'none' | 'country';

const SPLIT_OPTIONS = [
  { value: 'none', label: 'Total' },
  { value: 'country', label: 'By country' },
] as const;

/** Daily trending activity from /api/v1/overview/daily-volume (zero-filled by the API). */
export function VolumeTrendCard({ filters }: { filters: FilterParams }) {
  const [split, setSplit] = useState<Split>('none');
  const daily = useDailyVolume(filters, split === 'country' ? { split_by: 'country' } : {});

  return (
    <ChartCard
      title="Trending activity over time"
      description={
        split === 'none'
          ? 'Daily trending volume (snapshots) and distinct videos. Days without data show as zero.'
          : 'Daily trending volume per country.'
      }
      actions={
        <SegmentedControl
          label="Split trend"
          value={split}
          options={SPLIT_OPTIONS}
          onChange={setSplit}
        />
      }
    >
      <QueryState
        query={daily}
        loading={<LoadingState rows={6} label="Loading trend" />}
        isEmpty={(r) => r.data.series.every((s) => s.points.every((p) => p.trending_volume === 0))}
      >
        {({ data }) => {
          if (data.split_by === 'country') {
            const series = data.series.map((s, i) => ({
              key: s.key ?? `series-${i}`,
              label: s.key ?? 'All',
              color: seriesColor(i),
            }));
            const rows = pivotByDate(
              data.series.map((s, i) => ({ key: s.key ?? `series-${i}`, points: s.points })),
              (p) => p.trending_volume,
            );
            return (
              <div className="p-4">
                <TimeSeriesChart
                  data={rows}
                  series={series}
                  ariaLabel="Line chart of daily trending volume per country"
                />
              </div>
            );
          }
          const points = data.series[0]?.points ?? [];
          return (
            <div className="p-4">
              <TimeSeriesChart
                data={points.map((p) => ({
                  date: p.date,
                  trending_volume: p.trending_volume,
                  unique_videos: p.unique_videos,
                }))}
                series={[
                  { key: 'trending_volume', label: 'Trending volume', color: ACCENT },
                  { key: 'unique_videos', label: 'Unique videos', color: SECONDARY },
                ]}
                ariaLabel="Line chart of daily trending volume and unique videos"
              />
            </div>
          );
        }}
      </QueryState>
    </ChartCard>
  );
}
