/**
 * Typed API fixtures + MSW handlers for component tests. Every fixture is checked against the
 * generated OpenAPI types (`satisfies ApiResponse<…>`), so contract drift fails the typecheck.
 */
import { http, HttpResponse } from 'msw';

import type {
  ApiResponse,
  CurrentUser,
  HistoryPoint,
  Member,
  Role,
  VideoDetail,
  VideoListItem,
} from '../api/types';
import { config } from '../config';
import { server } from './msw/server';

export const BASE = config.apiBaseUrl;

export const appliedFilters = {
  start_date: '2025-12-07',
  end_date: '2026-01-05',
  days: 30,
  countries: [],
  categories: [],
} satisfies ApiResponse<'/api/v1/overview/kpis'>['filters'];

export const metaResponse = {
  data: {
    countries: [
      { code: 'GB', name: 'United Kingdom' },
      { code: 'IN', name: 'India' },
      { code: 'US', name: 'United States' },
    ],
    categories: ['Gaming', 'Music', 'News & Politics'],
    date_range: { min_date: '2024-10-12', max_date: '2026-01-05' },
    default_range: { start_date: '2025-12-07', end_date: '2026-01-05', days: 30 },
  },
} satisfies ApiResponse<'/api/v1/meta/filters'>;

export function kpisResponse(previousAvailable = true, uniqueVideos = 13213) {
  return {
    filters: appliedFilters,
    data: {
      period: { start_date: '2025-12-07', end_date: '2026-01-05', days: 30 },
      previous_period: {
        start_date: '2025-11-07',
        end_date: '2025-12-06',
        days: 30,
        available: previousAvailable,
      },
      unique_videos: {
        value: uniqueVideos,
        previous: previousAvailable ? 13949 : null,
        change_pct: previousAvailable ? -5.28 : null,
      },
      trending_volume: {
        value: 53668,
        previous: previousAvailable ? 53992 : null,
        change_pct: previousAvailable ? -0.6 : null,
      },
      views: {
        value: 6493963164,
        previous: previousAvailable ? 7160673398 : null,
        change_pct: previousAvailable ? -9.31 : null,
      },
      unique_channels: {
        value: 5133,
        previous: previousAvailable ? 5290 : null,
        change_pct: previousAvailable ? -2.97 : null,
      },
      engagement_rate: {
        value: 0.02955,
        previous: previousAvailable ? 0.02796 : null,
        change_pts: previousAvailable ? 0.1592 : null,
      },
    },
  } satisfies ApiResponse<'/api/v1/overview/kpis'>;
}

const days = ['2026-01-03', '2026-01-04', '2026-01-05'];

export function dailyResponse(splitBy: string | null) {
  const series =
    splitBy === 'country'
      ? ['GB', 'IN'].map((key) => ({
          key,
          points: days.map((date, i) => ({
            date,
            trending_volume: 100 + i,
            unique_videos: 90 + i,
          })),
        }))
      : splitBy === 'category'
        ? ['Gaming', 'Music'].map((key) => ({
            key,
            points: days.map((date, i) => ({
              date,
              trending_volume: 50 + i,
              unique_videos: 40 + i,
            })),
          }))
        : [
            {
              key: null,
              points: days.map((date, i) => ({
                date,
                trending_volume: 1800 + i,
                unique_videos: 1064 + i,
              })),
            },
          ];
  return {
    filters: appliedFilters,
    data: { split_by: splitBy as 'country' | 'category' | null, series },
  } satisfies ApiResponse<'/api/v1/overview/daily-volume'>;
}

export const categoriesResponse = {
  filters: appliedFilters,
  data: [
    {
      category: 'Gaming',
      trending_volume: 28870,
      volume_share_pct: 53.79,
      unique_videos: 7747,
      views: 2325966494,
      engagement_rate: 0.0332,
    },
    {
      category: 'Music',
      trending_volume: 12000,
      volume_share_pct: 22.36,
      unique_videos: 3000,
      views: 1500000000,
      engagement_rate: 0.025,
    },
  ],
} satisfies ApiResponse<'/api/v1/analytics/categories'>;

export const countriesResponse = {
  filters: appliedFilters,
  data: [
    {
      country_code: 'IN',
      country_name: 'India',
      trending_volume: 5988,
      unique_videos: 3417,
      views_of_trending_videos: 1786394996,
      engagement_rate: 0.031,
    },
    {
      country_code: 'US',
      country_name: 'United States',
      trending_volume: 5991,
      unique_videos: 4632,
      views_of_trending_videos: 2100000000,
      engagement_rate: 0.028,
    },
  ],
} satisfies ApiResponse<'/api/v1/analytics/countries'>;

export const engagementResponse = {
  filters: appliedFilters,
  data: {
    totals: {
      videos: 13213,
      videos_without_views: 29,
      views: 6493963164,
      likes: 172850522,
      comments: 19073535,
      engagement_rate: 0.02955,
    },
    distribution: { p25: 0.0141, p50: 0.0306, p75: 0.054, p90: 0.0805 },
    histogram: Array.from({ length: 11 }, (_, i) => ({
      lower_pct: i,
      upper_pct: i === 10 ? null : i + 1,
      videos: 100 * (11 - i),
    })),
    by_category: [
      {
        category: 'Gaming',
        videos: 7747,
        videos_with_views: 7740,
        p25: 0.02,
        p50: 0.035,
        p75: 0.06,
      },
    ],
    scatter: [
      {
        video_id: 'vid-1',
        title: 'Scatter video',
        category: 'Music',
        views: 101928772,
        engagement_rate: 0.0061,
      },
    ],
  },
} satisfies ApiResponse<'/api/v1/analytics/engagement'>;

export const channelsResponse = {
  filters: appliedFilters,
  data: [
    {
      channel_id: 'ch-1',
      channel_title: 'KAYE',
      subscribers: 2100000,
      unique_videos: 43,
      trending_volume: 400,
      views: 90000000,
      engagement_rate: 0.04,
    },
  ],
} satisfies ApiResponse<'/api/v1/analytics/channels'>;

export function videoItem(n: number, overrides: Partial<VideoListItem> = {}): VideoListItem {
  return {
    video_id: `vid-${n}`,
    title: `Video number ${n}`,
    channel_id: `ch-${n}`,
    channel_title: `Channel ${n}`,
    category: 'Music',
    thumbnail_url: `https://i.ytimg.com/vi/vid-${n}/default.jpg`,
    published_at: '2025-12-09T09:33:03',
    duration_sec: 229,
    views: 1_000_000 * n,
    likes: 1000 * n,
    comments: 100 * n,
    engagement_rate: 0.0011,
    trending_countries: ['GB', 'IN', 'NZ', 'US'],
    days_on_trending: 5,
    first_trending_date: '2025-12-10',
    last_trending_date: '2026-01-05',
    snapshot_count: 12,
    ...overrides,
  };
}

/** Server-side style paging over `total` generated videos (search matches titles). */
export function videoPage(url: URL, total = 60) {
  const page = Number(url.searchParams.get('page') ?? 1);
  const size = Number(url.searchParams.get('page_size') ?? 25);
  const search = url.searchParams.get('search');
  const all = Array.from({ length: total }, (_, i) => videoItem(i + 1)).filter(
    (v) => !search || (v.title ?? '').toLowerCase().includes(search.toLowerCase()),
  );
  const items = all.slice((page - 1) * size, page * size);
  return {
    filters: appliedFilters,
    data: {
      items,
      page,
      page_size: size,
      total: all.length,
      total_pages: Math.ceil(all.length / size),
    },
  } satisfies ApiResponse<'/api/v1/videos'>;
}

export function videoDetail(id = 'vid-1', overrides: Partial<VideoDetail> = {}): VideoDetail {
  return {
    video_id: id,
    title: 'Shararat | Dhurandhar',
    description: 'A fiery dance number.\n<script>alert(1)</script>',
    tags: 'dance, bollywood ,music',
    category: 'Music',
    published_at: '2025-12-09T09:33:03',
    duration_sec: 229,
    definition: 'hd',
    dimension: '2d',
    licensed_content: true,
    thumbnail_url: `https://i.ytimg.com/vi/${id}/default.jpg`,
    views: 101928772,
    likes: 613037,
    comments: 13490,
    engagement_rate: 0.006147,
    latest_country_code: 'IN',
    latest_trending_date: '2026-01-05',
    first_trending_date: '2025-12-09',
    last_trending_date: '2026-01-05',
    trending_countries: ['AU', 'IN', 'US'],
    snapshot_count: 3,
    channel: {
      channel_id: 'ch-1',
      title: 'Saregama Music',
      description: null,
      custom_url: '@saregamamusic',
      country: 'IN',
      published_at: '2006-01-01T00:00:00',
      subscribers: 60100000,
      hidden_subscribers: false,
      total_views: 50000000000,
      video_count: 20000,
    },
    ...overrides,
  };
}

export const historyRows: HistoryPoint[] = [
  {
    country_code: 'AU',
    country_name: 'Australia',
    trending_date: '2025-12-09',
    views: 2432863,
    likes: 54106,
    comments: 1463,
    engagement_rate: 0.0228,
  },
  {
    country_code: 'IN',
    country_name: 'India',
    trending_date: '2025-12-09',
    views: 2500000,
    likes: 55000,
    comments: 1500,
    engagement_rate: 0.0226,
  },
  {
    country_code: 'IN',
    country_name: 'India',
    trending_date: '2025-12-10',
    views: 9000000,
    likes: 90000,
    comments: 2000,
    engagement_rate: 0.0102,
  },
];

const PERMISSIONS: Record<Role, CurrentUser['user']['permissions']> = {
  OWNER: ['MAKE_PREDICTION', 'MANAGE_USERS', 'VIEW_ANALYTICS'],
  ADMIN: ['MAKE_PREDICTION', 'MANAGE_USERS', 'VIEW_ANALYTICS'],
  MEMBER: ['MAKE_PREDICTION', 'VIEW_ANALYTICS'],
};

export const USER_IDS = {
  self: '00000000-0000-4000-8000-000000000001',
  owner: '00000000-0000-4000-8000-000000000002',
  admin: '00000000-0000-4000-8000-000000000003',
  member: '00000000-0000-4000-8000-000000000004',
};

export function currentUser(role: Role = 'MEMBER'): CurrentUser {
  return {
    user: {
      id: USER_IDS.self,
      email: 'pat@example.com',
      display_name: 'Pat Example',
      role,
      permissions: PERMISSIONS[role],
    },
    tenant: { id: '00000000-0000-4000-8000-0000000000aa', name: 'Acme Analytics' },
  };
}

export function member(id: string, role: Role, overrides: Partial<Member> = {}): Member {
  return {
    id,
    email: `${role.toLowerCase()}@example.com`,
    display_name: `${role[0]}${role.slice(1).toLowerCase()} Person`,
    role,
    is_active: true,
    created_at: '2026-01-01T10:00:00Z',
    last_login_at: '2026-01-05T09:00:00Z',
    ...overrides,
  };
}

export function notAuthenticated() {
  return errorEnvelope('not_authenticated', 'Authentication required.', 401);
}

/**
 * Registers handlers for every GET endpoint and records each request URL.
 * Tests can override any endpoint afterwards with `server.use(...)` (newest handler wins).
 *
 * `user` is who /auth/me reports (default: a signed-in MEMBER); null means signed out.
 */
export function mockApi({ user = currentUser() }: { user?: CurrentUser | null } = {}) {
  const requests: URL[] = [];
  const recorded =
    <T>(respond: (url: URL) => T) =>
    ({ request }: { request: Request }) => {
      const url = new URL(request.url);
      requests.push(url);
      return HttpResponse.json(respond(url) as Record<string, unknown>);
    };

  server.use(
    // Not recorded in `requests`: data-request assertions stay independent of the session check.
    http.get(`${BASE}/api/v1/auth/me`, () =>
      user ? HttpResponse.json({ data: user }) : notAuthenticated(),
    ),
    http.get(
      `${BASE}/api/v1/meta/filters`,
      recorded(() => metaResponse),
    ),
    http.get(
      `${BASE}/api/v1/overview/kpis`,
      recorded(() => kpisResponse()),
    ),
    http.get(
      `${BASE}/api/v1/overview/daily-volume`,
      recorded((url) => dailyResponse(url.searchParams.get('split_by'))),
    ),
    http.get(
      `${BASE}/api/v1/analytics/categories`,
      recorded(() => categoriesResponse),
    ),
    http.get(
      `${BASE}/api/v1/analytics/countries`,
      recorded(() => countriesResponse),
    ),
    http.get(
      `${BASE}/api/v1/analytics/engagement`,
      recorded(() => engagementResponse),
    ),
    http.get(
      `${BASE}/api/v1/analytics/channels`,
      recorded(() => channelsResponse),
    ),
    http.get(
      `${BASE}/api/v1/videos`,
      recorded((url) => videoPage(url)),
    ),
    http.get(
      `${BASE}/api/v1/videos/:videoId`,
      recorded((url) => ({
        data: videoDetail(decodeURIComponent(url.pathname.split('/').pop() ?? '')),
      })),
    ),
    http.get(
      `${BASE}/api/v1/videos/:videoId/history`,
      recorded(() => ({ data: historyRows })),
    ),
    http.get(
      `${BASE}/api/v1/predictions/model-info`,
      recorded(() => modelInfoResponse),
    ),
    http.post(
      `${BASE}/api/v1/predictions`,
      recorded(() => predictionResponse()),
    ),
  );

  return {
    requests,
    /** Requests made to one API path, e.g. calls('/api/v1/overview/kpis'). */
    calls: (path: string) => requests.filter((u) => u.pathname === path),
  };
}

export function errorEnvelope(
  code: string,
  message: string,
  status: number,
  field: string | null = null,
  details?: { field: string | null; message: string }[],
) {
  return HttpResponse.json(
    { error: { code, message, field, request_id: 'req-test-1', ...(details ? { details } : {}) } },
    { status },
  );
}

export const modelInfoResponse = {
  data: {
    name: 'YouTube trending high-performance model (frozen)',
    version: '8c2a4a05c1f6',
    output: 'high_performance_probability',
    label_definition:
      'Trained only on videos that were already on a YouTube trending list. A video is labelled high-performing when its likes and comments are at or above its country median.',
    not_a_prediction_of:
      'It does not estimate whether an arbitrary video will reach a trending list.',
    training_data: 'Trending videos from AU, CA, GB, IE, IN, NZ, US and ZA.',
    supported_countries: ['AU', 'CA', 'GB', 'IE', 'IN', 'NZ', 'US', 'ZA'],
    supported_categories: ['Gaming', 'Music', 'Sports'],
    category_input: 'Category name (case-insensitive) or YouTube category ID.',
    components: {
      text: 'Text sub-model description.',
      channel_and_numeric: 'Channel sub-model description.',
      psychology: 'Title-signal sub-model description.',
      high_performance_probability: 'Combination of the three component scores.',
    },
    reported_metrics: { roc_auc: '0.894', note: 'Reported on the training notebook split.' },
    limitations: ['Singapore (SG) is not supported.', 'Some title signals are fixed at 0.'],
  },
} satisfies ApiResponse<'/api/v1/predictions/model-info'>;

export function predictionResponse(probability = 0.938877798492448) {
  return {
    data: {
      high_performance_probability: probability,
      components: { text: 0.8145, channel_and_numeric: 0.8209, psychology: 0.5634 },
      inputs_used: { category: 'Sports', country: 'IN' },
      model: { version: '8c2a4a05c1f6', label_definition: 'Label definition from the API.' },
    },
  } satisfies ApiResponse<'/api/v1/predictions', 'post'>;
}
