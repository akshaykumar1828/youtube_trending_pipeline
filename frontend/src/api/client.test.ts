// @vitest-environment node
import { delay, http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { config } from '../config';
import { server } from '../test/msw/server';
import {
  apiClient,
  callApi,
  createApiClient,
  generateRequestId,
  PREDICTION_TIMEOUT_MS,
} from './client';
import { ApiError } from './errors';
import type { ApiResponse, PredictionRequest } from './types';

const BASE = config.apiBaseUrl;
const KPIS_URL = `${BASE}/api/v1/overview/kpis`;

// Typed against the generated contract: a shape drift fails `npm run typecheck`.
const kpisBody: ApiResponse<'/api/v1/overview/kpis'> = {
  filters: {
    start_date: '2025-12-07',
    end_date: '2026-01-05',
    days: 30,
    countries: ['IN'],
    categories: [],
  },
  data: {
    period: { start_date: '2025-12-07', end_date: '2026-01-05', days: 30 },
    previous_period: {
      start_date: '2025-11-07',
      end_date: '2025-12-06',
      days: 30,
      available: true,
    },
    unique_videos: { value: 3417, previous: 3635, change_pct: -5.997 },
    trending_volume: { value: 5988, previous: 5998, change_pct: -0.167 },
    views: { value: 1786394996, previous: 1982496770, change_pct: -9.892 },
    unique_channels: { value: 1511, previous: 1599, change_pct: -5.503 },
    engagement_rate: { value: 0.031, previous: 0.029, change_pts: 0.2 },
  },
};

const getKpis = (query = {}, options = {}) =>
  callApi(
    (init) => apiClient.GET('/api/v1/overview/kpis', { params: { query }, ...init }),
    options,
  );

describe('fetch resolution', () => {
  it('uses the fetch installed after the client was created (MSW, instrumentation)', async () => {
    // Regression guard: openapi-fetch would otherwise capture globalThis.fetch at import time,
    // sending test requests past MSW to the real network.
    const replaced = vi.fn(async () => HttpResponse.json(kpisBody));
    vi.stubGlobal('fetch', replaced);
    try {
      await getKpis();
    } finally {
      vi.unstubAllGlobals();
    }
    expect(replaced).toHaveBeenCalledTimes(1);
  });
});

describe('callApi: successful typed requests', () => {
  it('returns the typed success envelope', async () => {
    server.use(http.get(KPIS_URL, () => HttpResponse.json(kpisBody)));
    const body = await getKpis();
    expect(body).toEqual(kpisBody);
    const change: number | null = body.data.engagement_rate.change_pts; // compile-time typing
    expect(change).toBe(0.2);
  });

  it('uses the configured base URL', async () => {
    const other = createApiClient('http://api.example.test');
    server.use(
      http.get('http://api.example.test/api/v1/meta/filters', () =>
        HttpResponse.json({
          data: {
            countries: [{ code: 'IN', name: 'India' }],
            categories: ['Music'],
            date_range: { min_date: '2024-10-12', max_date: '2026-01-05' },
            default_range: { start_date: '2025-12-07', end_date: '2026-01-05', days: 30 },
          },
        } satisfies ApiResponse<'/api/v1/meta/filters'>),
      ),
    );
    const body = await callApi((init) => other.GET('/api/v1/meta/filters', init));
    expect(body.data.countries[0]?.code).toBe('IN');
    expect(BASE).toBe('http://localhost:8000');
  });

  it('encodes path parameters', async () => {
    let path = '';
    server.use(
      http.get(`${BASE}/api/v1/videos/:videoId/history`, ({ request }) => {
        path = new URL(request.url).pathname;
        return HttpResponse.json({
          data: [],
        } satisfies ApiResponse<'/api/v1/videos/{video_id}/history'>);
      }),
    );
    await callApi((init) =>
      apiClient.GET('/api/v1/videos/{video_id}/history', {
        params: { path: { video_id: 'a b/c' } },
        ...init,
      }),
    );
    expect(path).toBe('/api/v1/videos/a%20b%2Fc/history');
  });

  it('sends typed POST bodies', async () => {
    let received: unknown;
    server.use(
      http.post(`${BASE}/api/v1/predictions`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({
          data: {
            high_performance_probability: 0.93,
            components: { text: 0.81 },
            inputs_used: { category: 'Sports', country: 'IN' },
            model: { version: '8c2a4a05c1f6', label_definition: 'definition' },
          },
        } satisfies ApiResponse<'/api/v1/predictions', 'post'>);
      }),
    );
    const request: PredictionRequest = {
      title: 'Match highlights',
      category: 17,
      country: 'IN',
      duration_sec: 140,
      channel_subscriber_count: 1000,
      channel_video_count: 10,
      channel_view_count: 50000,
      tags: ['cricket', 'highlights'],
    };
    const body = await callApi(
      (init) => apiClient.POST('/api/v1/predictions', { body: request, ...init }),
      { timeoutMs: PREDICTION_TIMEOUT_MS },
    );
    expect(received).toEqual(request);
    expect(body.data.high_performance_probability).toBe(0.93);
  });
});

describe('query parameter serialization', () => {
  it('sends arrays as repeated keys, as FastAPI expects', async () => {
    let url: URL | undefined;
    server.use(
      http.get(KPIS_URL, ({ request }) => {
        url = new URL(request.url);
        return HttpResponse.json(kpisBody);
      }),
    );
    await getKpis({
      start_date: '2025-12-07',
      country: ['IN', 'US'],
      category: ['Music', 'News & Politics'],
    });
    expect(url?.searchParams.getAll('country')).toEqual(['IN', 'US']);
    expect(url?.searchParams.getAll('category')).toEqual(['Music', 'News & Politics']);
    expect(url?.searchParams.get('start_date')).toBe('2025-12-07');
    expect(url?.search).toContain('country=IN&country=US');
    expect(url?.search).not.toMatch(/country=IN(%2C|,)US/);
  });

  it('omits parameters that are not provided', async () => {
    let search = 'unset';
    server.use(
      http.get(KPIS_URL, ({ request }) => {
        search = new URL(request.url).search;
        return HttpResponse.json(kpisBody);
      }),
    );
    await getKpis({});
    expect(search).toBe('');
  });

  it('serializes enum and numeric parameters of the video list', async () => {
    let url: URL | undefined;
    server.use(
      http.get(`${BASE}/api/v1/videos`, ({ request }) => {
        url = new URL(request.url);
        return HttpResponse.json({
          filters: kpisBody.filters,
          data: { items: [], page: 2, page_size: 50, total: 0, total_pages: 0 },
        } satisfies ApiResponse<'/api/v1/videos'>);
      }),
    );
    await callApi((init) =>
      apiClient.GET('/api/v1/videos', {
        params: { query: { sort: 'engagement_rate', order: 'asc', page: 2, page_size: 50 } },
        ...init,
      }),
    );
    expect(Object.fromEntries(url?.searchParams ?? [])).toEqual({
      sort: 'engagement_rate',
      order: 'asc',
      page: '2',
      page_size: '50',
    });
  });
});

describe('request IDs', () => {
  it('sends a fresh X-Request-ID with every request', async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get(KPIS_URL, ({ request }) => {
        seen.push(request.headers.get('x-request-id'));
        return HttpResponse.json(kpisBody);
      }),
    );
    await getKpis();
    await getKpis();
    expect(seen).toHaveLength(2);
    for (const id of seen) expect(id).toMatch(/^[0-9a-f]{32}$/);
    expect(seen[0]).not.toBe(seen[1]);
  });

  it('generates ids the backend accepts ([A-Za-z0-9._-]{1,64})', () => {
    const ids = new Set(Array.from({ length: 200 }, generateRequestId));
    expect(ids.size).toBe(200);
    for (const id of ids) expect(id).toMatch(/^[A-Za-z0-9._-]{1,64}$/);
  });
});

describe('error normalization', () => {
  it('maps the backend error envelope', async () => {
    server.use(
      http.get(KPIS_URL, () =>
        HttpResponse.json(
          {
            error: {
              code: 'invalid_filter',
              message: "countries: unknown ['XX']",
              field: 'countries',
              request_id: 'server-id-1',
            },
          },
          { status: 422, headers: { 'X-Request-ID': 'server-id-1' } },
        ),
      ),
    );
    const error = await getKpis({ country: ['XX'] }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: 'invalid_filter',
      message: "countries: unknown ['XX']",
      field: 'countries',
      requestId: 'server-id-1',
      details: [],
    });
  });

  it('keeps field-level details from validation errors', async () => {
    server.use(
      http.get(KPIS_URL, () =>
        HttpResponse.json(
          {
            error: {
              code: 'invalid_request',
              message: 'The request is invalid.',
              field: 'start_date',
              request_id: 'r2',
              details: [{ field: 'start_date', message: 'Input should be a valid date' }],
            },
          },
          { status: 422 },
        ),
      ),
    );
    const error = (await getKpis().catch((e: unknown) => e)) as ApiError;
    expect(error.details).toEqual([
      { field: 'start_date', message: 'Input should be a valid date' },
    ]);
  });

  it.each([
    [404, 'not_found'],
    [503, 'database_unavailable'],
    [504, 'query_timeout'],
  ])('maps HTTP %i envelope to code %s', async (status, code) => {
    server.use(
      http.get(KPIS_URL, () =>
        HttpResponse.json({ error: { code, message: 'x', request_id: 'r' } }, { status }),
      ),
    );
    await expect(getKpis()).rejects.toMatchObject({ status, code });
  });

  it('falls back to http_error for non-envelope responses, using the response request id', async () => {
    server.use(
      http.get(KPIS_URL, () =>
        HttpResponse.text('<html>Bad gateway</html>', {
          status: 502,
          headers: { 'X-Request-ID': 'header-id' },
        }),
      ),
    );
    await expect(getKpis()).rejects.toMatchObject({
      status: 502,
      code: 'http_error',
      requestId: 'header-id',
    });
  });

  it('uses the sent request id when the response has none', async () => {
    let sent: string | null = null;
    server.use(
      http.get(KPIS_URL, ({ request }) => {
        sent = request.headers.get('x-request-id');
        return HttpResponse.json({ status: 'not_ready' }, { status: 503 });
      }),
    );
    const error = (await getKpis().catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe('http_error');
    expect(error.requestId).toBe(sent);
  });

  it('treats an empty success body as invalid_response', async () => {
    server.use(http.get(KPIS_URL, () => HttpResponse.json(null)));
    await expect(getKpis()).rejects.toMatchObject({ status: 200, code: 'invalid_response' });
  });

  it('maps network failures to network_error with the sent request id', async () => {
    let sent: string | null = null;
    server.use(
      http.get(KPIS_URL, ({ request }) => {
        sent = request.headers.get('x-request-id');
        return HttpResponse.error();
      }),
    );
    const error = (await getKpis().catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: 'network_error' });
    expect(error.requestId).toBe(sent);
  });
});

describe('timeouts and cancellation', () => {
  it('rejects with a timeout ApiError when the response is too slow', async () => {
    server.use(
      http.get(KPIS_URL, async () => {
        await delay(1000);
        return HttpResponse.json(kpisBody);
      }),
    );
    const started = Date.now();
    const error = (await getKpis({}, { timeoutMs: 50 }).catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: 'timeout' });
    expect(error.requestId).toMatch(/^[0-9a-f]{32}$/);
    expect(Date.now() - started).toBeLessThan(900);
  });

  it('re-throws caller cancellation unchanged (not an ApiError)', async () => {
    server.use(
      http.get(KPIS_URL, async () => {
        await delay(1000);
        return HttpResponse.json(kpisBody);
      }),
    );
    const controller = new AbortController();
    const pending = getKpis({}, { signal: controller.signal });
    controller.abort();
    const error = await pending.catch((e: unknown) => e);
    expect(error).not.toBeInstanceOf(ApiError);
    expect((error as Error).name).toBe('AbortError');
  });
});
