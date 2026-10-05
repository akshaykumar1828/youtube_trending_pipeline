import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

import type { SortOrder, VideoListParams, VideoSort } from '../../api/types';

/** Labels for every backend sort key. Typed against the generated union, so the list stays exhaustive. */
export const SORT_LABELS: Record<VideoSort, string> = {
  views: 'Views',
  likes: 'Likes',
  comments: 'Comments',
  engagement_rate: 'Engagement rate',
  days_on_trending: 'Days on trending',
  first_trending_date: 'First trending date',
  last_trending_date: 'Last trending date',
  published_at: 'Publish date',
};

export const PAGE_SIZES = [25, 50, 100] as const;
const ORDERS: readonly SortOrder[] = ['desc', 'asc'];

/** API defaults (sort=views, order=desc, page=1, page_size=25). */
const DEFAULTS = { sort: 'views', order: 'desc', page: 1, page_size: 25 } as const;

function isSort(value: string | null): value is VideoSort {
  return value !== null && value in SORT_LABELS;
}

/**
 * Video-list state in the URL (search, sort, order, page, page_size). Unknown values fall back
 * to the API defaults; the backend still validates everything it receives.
 */
export function useVideoListParams() {
  const [searchParams, setSearchParams] = useSearchParams();

  const params = useMemo(() => {
    const sort = searchParams.get('sort');
    const order = searchParams.get('order');
    const page = Number(searchParams.get('page'));
    const pageSize = Number(searchParams.get('page_size'));
    const search = searchParams.get('search')?.trim() ?? '';
    return {
      sort: isSort(sort) ? sort : DEFAULTS.sort,
      order: ORDERS.includes(order as SortOrder) ? (order as SortOrder) : DEFAULTS.order,
      page: Number.isInteger(page) && page >= 1 ? page : DEFAULTS.page,
      page_size: (PAGE_SIZES as readonly number[]).includes(pageSize)
        ? pageSize
        : DEFAULTS.page_size,
      search,
    };
  }, [searchParams]);

  const apiParams: VideoListParams = useMemo(
    () => ({
      sort: params.sort,
      order: params.order,
      page: params.page,
      page_size: params.page_size,
      ...(params.search ? { search: params.search } : {}),
    }),
    [params],
  );

  const update = useCallback(
    (patch: Record<string, string | number | null>, resetPage = true) => {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        for (const [key, value] of Object.entries(patch)) {
          if (value === null || value === '') next.delete(key);
          else next.set(key, String(value));
        }
        if (resetPage) next.delete('page');
        return next;
      });
    },
    [setSearchParams],
  );

  return {
    params,
    apiParams,
    setSearch: (search: string) => update({ search: search.trim() || null }),
    setSort: (sort: VideoSort) => update({ sort }),
    setOrder: (order: SortOrder) => update({ order }),
    setPageSize: (pageSize: number) => update({ page_size: pageSize }),
    setPage: (page: number) => update({ page: page > 1 ? page : null }, false),
  };
}
