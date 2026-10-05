import { ArrowLeft, ExternalLink, Info } from 'lucide-react';
import { Link, useParams } from 'react-router';

import { isApiError } from '../../api/errors';
import type { HistoryPoint, VideoDetail } from '../../api/types';
import { seriesColor } from '../../components/charts/chartTheme';
import { pivotByDate } from '../../components/charts/pivot';
import { TimeSeriesChart } from '../../components/charts/TimeSeriesChart';
import { ChartCard } from '../../components/data/ChartCard';
import { DataTable, type Column } from '../../components/data/DataTable';
import { QueryState } from '../../components/data/QueryState';
import { StatTile } from '../../components/data/StatTile';
import { EmptyState, LoadingState } from '../../components/data/states';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import {
  formatCompact,
  formatDate,
  formatDuration,
  formatInteger,
  formatRate,
} from '../../lib/format';
import { APP_NAME } from '../../layouts/PageHeader';
import { useGlobalFilters } from '../filters/useGlobalFilters';
import { useVideo, useVideoHistory } from './queries';
import { Thumbnail } from './VideoTable';

/** YouTube's standard watch URL for a video ID (the ID is YouTube's own, from the Data API). */
function youtubeUrl(videoId: string): string {
  return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`;
}

const historyColumns: Column<HistoryPoint>[] = [
  {
    key: 'date',
    header: 'Date',
    cell: (h) => <span className="whitespace-nowrap">{formatDate(h.trending_date)}</span>,
  },
  { key: 'country', header: 'Country', cell: (h) => h.country_name ?? h.country_code },
  { key: 'views', header: 'Views', align: 'right', cell: (h) => formatInteger(h.views) },
  { key: 'likes', header: 'Likes', align: 'right', cell: (h) => formatInteger(h.likes) },
  { key: 'comments', header: 'Comments', align: 'right', cell: (h) => formatInteger(h.comments) },
  {
    key: 'engagement',
    header: 'Engagement',
    align: 'right',
    cell: (h) => formatRate(h.engagement_rate),
  },
];

function TrendingHistory({ videoId }: { videoId: string }) {
  const history = useVideoHistory(videoId);
  return (
    <ChartCard
      title="Trending history"
      description="Every trending snapshot in every country (not affected by dashboard filters). Views are YouTube's global lifetime count at each snapshot, so country lines usually overlap."
    >
      <QueryState
        query={history}
        loading={<LoadingState rows={6} label="Loading trending history" />}
        isEmpty={(rows) => rows.length === 0}
        emptyTitle="No trending history recorded"
        emptyDescription="This video has no trending snapshots."
      >
        {(rows) => {
          const byCountry = new Map<string, HistoryPoint[]>();
          for (const row of rows) {
            byCountry.set(row.country_code, [...(byCountry.get(row.country_code) ?? []), row]);
          }
          const series = [...byCountry.entries()].map(([code, points]) => ({
            key: code,
            points: points.map((p) => ({ date: p.trending_date, views: p.views })),
          }));
          return (
            <>
              <div className="border-b border-slate-100 p-4">
                <TimeSeriesChart
                  data={pivotByDate(series, (p) => p.views)}
                  series={series.map((s, i) => ({
                    key: s.key,
                    label: s.key,
                    color: seriesColor(i),
                  }))}
                  ariaLabel="Line chart of the video's view count at each trending snapshot, per country"
                />
              </div>
              <div className="max-h-96 overflow-y-auto">
                <DataTable
                  columns={historyColumns}
                  rows={rows}
                  rowKey={(h) => `${h.trending_date}-${h.country_code}`}
                  caption="Trending snapshots by date and country"
                />
              </div>
            </>
          );
        }}
      </QueryState>
    </ChartCard>
  );
}

function VideoContent({ video }: { video: VideoDetail }) {
  const tags = (video.tags ?? '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  return (
    <>
      <title>{`${video.title ?? video.video_id} · ${APP_NAME}`}</title>
      <Card className="p-4">
        <div className="flex flex-col gap-4 sm:flex-row">
          <Thumbnail src={video.thumbnail_url} size="lg" />
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-semibold tracking-tight text-slate-900">
              {video.title ?? video.video_id}
            </h1>
            <p className="mt-0.5 text-sm text-slate-600">
              {video.channel.title ?? 'Unknown channel'}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-500">
              <Badge tone="accent">{video.category}</Badge>
              <span>Published {formatDate(video.published_at)}</span>
              <span>Duration {formatDuration(video.duration_sec)}</span>
              <span className="font-mono">{video.video_id}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-start">
            <a
              href={youtubeUrl(video.video_id)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-9 items-center gap-2 rounded-md bg-accent-600 px-3 text-sm font-medium text-white hover:bg-accent-700"
            >
              Open on YouTube
              <ExternalLink aria-hidden="true" className="size-4" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </div>
        </div>
        <p className="mt-4 flex items-start gap-2 text-xs text-slate-500">
          <Info aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          All-time data from this video’s latest snapshot (latest date, then highest views).
          Dashboard filters do not apply on this page.
        </p>
      </Card>

      <section aria-label="Latest metrics">
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile
            label="Views"
            value={formatCompact(video.views)}
            hint={formatInteger(video.views)}
          />
          <StatTile
            label="Likes"
            value={formatCompact(video.likes)}
            hint={formatInteger(video.likes)}
          />
          <StatTile
            label="Comments"
            value={formatCompact(video.comments)}
            hint={formatInteger(video.comments)}
          />
          <StatTile
            label="Engagement rate"
            value={formatRate(video.engagement_rate)}
            hint="(Likes + comments) / views"
          />
        </dl>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartCard title="Trending summary" className="xl:col-span-2">
          <dl className="grid grid-cols-2 gap-3 p-4 md:grid-cols-4">
            <StatTile label="First trending" value={formatDate(video.first_trending_date)} />
            <StatTile label="Last trending" value={formatDate(video.last_trending_date)} />
            <StatTile
              label="Trending appearances"
              value={formatInteger(video.snapshot_count)}
              hint="Country × day snapshots"
            />
            <StatTile label="Latest snapshot country" value={video.latest_country_code} />
          </dl>
          <div className="flex flex-wrap items-center gap-1.5 px-4 pb-4">
            <span className="text-xs text-slate-500">Trended in:</span>
            {video.trending_countries.map((code) => (
              <Badge key={code} className="font-mono">
                {code}
              </Badge>
            ))}
          </div>
        </ChartCard>

        <ChartCard title="Channel">
          <dl className="space-y-2 p-4 text-sm">
            {[
              ['Name', video.channel.title ?? '—'],
              [
                'Subscribers',
                video.channel.hidden_subscribers
                  ? 'Hidden'
                  : formatInteger(video.channel.subscribers),
              ],
              ['Channel views', formatInteger(video.channel.total_views)],
              ['Videos', formatInteger(video.channel.video_count)],
              ['Country', video.channel.country ?? '—'],
              ['Handle', video.channel.custom_url ?? '—'],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4">
                <dt className="text-slate-500">{label}</dt>
                <dd className="truncate text-right font-medium text-slate-800 tabular-nums">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </ChartCard>
      </div>

      <TrendingHistory videoId={video.video_id} />

      {(video.description || tags.length > 0) && (
        <ChartCard title="Description and tags">
          <div className="space-y-3 p-4">
            {video.description && (
              <details>
                <summary className="cursor-pointer text-xs font-medium text-accent-700">
                  Show description
                </summary>
                {/* Rendered as plain text; React escapes it (no HTML is interpreted). */}
                <p className="mt-2 text-sm whitespace-pre-wrap text-slate-700">
                  {video.description}
                </p>
              </details>
            )}
            {tags.length > 0 && (
              <ul aria-label="Tags" className="flex flex-wrap gap-1.5">
                {tags.map((tag, i) => (
                  <li key={`${tag}-${i}`}>
                    <Badge>{tag}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </ChartCard>
      )}
    </>
  );
}

export function VideoDetailPage() {
  const { videoId = '' } = useParams();
  const { search } = useGlobalFilters();
  const video = useVideo(videoId);
  const notFound = isApiError(video.error) && video.error.status === 404;

  return (
    <>
      <Link
        to={`/trending${search}`}
        className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" />
        Trending videos
      </Link>
      {notFound ? (
        <Card>
          <title>{`Video not found · ${APP_NAME}`}</title>
          <EmptyState
            title="Video not found"
            description={`No video with ID “${videoId}” exists in the trending data.`}
            action={
              <Link
                to={`/trending${search}`}
                className="text-sm font-medium text-accent-700 hover:underline"
              >
                Browse trending videos
              </Link>
            }
          />
        </Card>
      ) : (
        <QueryState
          query={video}
          loading={
            <Card>
              <LoadingState rows={8} label="Loading video" />
            </Card>
          }
        >
          {(data) => <VideoContent video={data} />}
        </QueryState>
      )}
    </>
  );
}
