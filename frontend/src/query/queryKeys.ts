import type {
  ChannelParams,
  DailyVolumeParams,
  EngagementParams,
  FilterParams,
  VideoListParams,
} from '../api/types';

/** Filters as they appear in query keys: empty values removed, arrays de-duplicated and sorted. */
export interface NormalizedFilters {
  start_date?: string;
  end_date?: string;
  country?: string[];
  category?: string[];
}

function normalizeList(values: string[] | null | undefined): string[] | undefined {
  if (!values || values.length === 0) return undefined;
  return [...new Set(values)].sort();
}

/**
 * Normalizes global filters for cache keys only. Array order and duplicates do not change the
 * backend result, so ['US','IN'] and ['IN','US'] share one cache entry. Values are otherwise
 * passed through unchanged: the backend remains the authority for validation and defaults.
 */
export function normalizeFilters(filters: FilterParams = {}): NormalizedFilters {
  const normalized: NormalizedFilters = {};
  if (filters.start_date) normalized.start_date = filters.start_date;
  if (filters.end_date) normalized.end_date = filters.end_date;
  const country = normalizeList(filters.country);
  if (country) normalized.country = country;
  const category = normalizeList(filters.category);
  if (category) normalized.category = category;
  return normalized;
}

/** Drops undefined/null entries so omitted and explicitly-empty params produce the same key. */
function compact<T extends object>(params: T | undefined): Partial<T> {
  if (!params) return {};
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null),
  ) as Partial<T>;
}

/**
 * Central query-key factory. Keys are hierarchical (['overview', ...], ['videos', ...]) so a
 * whole group can be invalidated, and every filtered key includes the normalized global filters.
 */
export const queryKeys = {
  auth: {
    all: ['auth'] as const,
    me: () => ['auth', 'me'] as const,
  },
  tenant: {
    all: ['tenant'] as const,
    detail: () => ['tenant', 'detail'] as const,
    members: () => ['tenant', 'members'] as const,
  },
  meta: {
    all: ['meta'] as const,
    filters: () => ['meta', 'filters'] as const,
  },
  overview: {
    all: ['overview'] as const,
    kpis: (filters?: FilterParams) => ['overview', 'kpis', normalizeFilters(filters)] as const,
    dailyVolume: (filters?: FilterParams, params?: DailyVolumeParams) =>
      ['overview', 'daily-volume', normalizeFilters(filters), compact(params)] as const,
  },
  analytics: {
    all: ['analytics'] as const,
    categories: (filters?: FilterParams) =>
      ['analytics', 'categories', normalizeFilters(filters)] as const,
    countries: (filters?: FilterParams) =>
      ['analytics', 'countries', normalizeFilters(filters)] as const,
    engagement: (filters?: FilterParams, params?: EngagementParams) =>
      ['analytics', 'engagement', normalizeFilters(filters), compact(params)] as const,
    channels: (filters?: FilterParams, params?: ChannelParams) =>
      ['analytics', 'channels', normalizeFilters(filters), compact(params)] as const,
  },
  videos: {
    all: ['videos'] as const,
    list: (filters?: FilterParams, params?: VideoListParams) =>
      ['videos', 'list', normalizeFilters(filters), compact(params)] as const,
    detail: (videoId: string) => ['videos', 'detail', videoId] as const,
    history: (videoId: string) => ['videos', 'history', videoId] as const,
  },
  predictions: {
    all: ['predictions'] as const,
    modelInfo: () => ['predictions', 'model-info'] as const,
  },
} as const;
