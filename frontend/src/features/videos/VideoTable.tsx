import { ImageOff } from 'lucide-react';
import { Link } from 'react-router';

import type { VideoListItem } from '../../api/types';
import { DataTable, type Column } from '../../components/data/DataTable';
import { Badge } from '../../components/ui/Badge';
import { formatCompact, formatDate, formatInteger, formatRate } from '../../lib/format';
import { videoPath } from './paths';

export function Thumbnail({ src, size = 'sm' }: { src: string | null; size?: 'sm' | 'lg' }) {
  const box = size === 'sm' ? 'h-9 w-12' : 'h-[90px] w-[120px]';
  if (!src) {
    return (
      <span className={`grid ${box} shrink-0 place-items-center rounded bg-slate-100`}>
        <ImageOff aria-hidden="true" className="size-4 text-slate-400" />
      </span>
    );
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      className={`${box} shrink-0 rounded bg-slate-100 object-cover`}
    />
  );
}

function Countries({ codes }: { codes: string[] }) {
  const shown = codes.slice(0, 3);
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((code) => (
        <Badge key={code} className="font-mono">
          {code}
        </Badge>
      ))}
      {codes.length > shown.length && (
        <Badge title={codes.slice(3).join(', ')}>+{codes.length - shown.length}</Badge>
      )}
    </span>
  );
}

interface VideoTableProps {
  items: VideoListItem[];
  /** Global filter query string, carried into the detail link. */
  search: string;
  compact?: boolean;
  caption: string;
}

/** Video rows as returned by /api/v1/videos (latest snapshot within the filters). */
export function VideoTable({ items, search, compact = false, caption }: VideoTableProps) {
  const columns: Column<VideoListItem>[] = [
    {
      key: 'video',
      header: 'Video',
      cell: (v) => (
        <div className="flex max-w-md min-w-64 items-center gap-3">
          <Thumbnail src={v.thumbnail_url} />
          <div className="min-w-0">
            <Link
              to={videoPath(v.video_id, search)}
              className="line-clamp-2 font-medium text-slate-900 hover:text-accent-700 hover:underline"
            >
              {v.title ?? v.video_id}
            </Link>
            <p className="truncate text-xs text-slate-500">{v.channel_title ?? '—'}</p>
          </div>
        </div>
      ),
    },
    { key: 'category', header: 'Category', cell: (v) => <Badge>{v.category}</Badge> },
    {
      key: 'countries',
      header: 'Trending in',
      cell: (v) => <Countries codes={v.trending_countries} />,
      className: compact ? 'hidden md:table-cell' : undefined,
    },
    {
      key: 'views',
      header: 'Views',
      align: 'right',
      cell: (v) => <span title={formatInteger(v.views)}>{formatCompact(v.views)}</span>,
    },
    {
      key: 'engagement',
      header: 'Engagement',
      align: 'right',
      cell: (v) => formatRate(v.engagement_rate),
    },
  ];
  if (!compact) {
    columns.push(
      {
        key: 'days',
        header: 'Days trending',
        align: 'right',
        cell: (v) => formatInteger(v.days_on_trending),
        className: 'hidden lg:table-cell',
      },
      {
        key: 'last',
        header: 'Last trending',
        cell: (v) => <span className="whitespace-nowrap">{formatDate(v.last_trending_date)}</span>,
        className: 'hidden md:table-cell',
      },
    );
  }
  return <DataTable columns={columns} rows={items} rowKey={(v) => v.video_id} caption={caption} />;
}
