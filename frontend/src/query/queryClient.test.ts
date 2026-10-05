// @vitest-environment node
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { apiClient, callApi } from '../api/client';
import { ApiError } from '../api/errors';
import { config } from '../config';
import { server } from '../test/msw/server';
import {
  createQueryClient,
  GC_TIME,
  retryDelay,
  shouldRetryQuery,
  STALE_TIME,
} from './queryClient';
import { queryKeys } from './queryKeys';

const apiError = (status: number, code: string) =>
  new ApiError({ status, code, message: code, requestId: 'r' });

describe('QueryClient defaults', () => {
  it('uses the configured stale/gc times and disables focus refetching', () => {
    const client = createQueryClient();
    const { queries, mutations } = client.getDefaultOptions();
    expect(queries?.staleTime).toBe(5 * 60_000);
    expect(queries?.gcTime).toBe(GC_TIME);
    expect(GC_TIME).toBe(30 * 60_000);
    expect(queries?.refetchOnWindowFocus).toBe(false);
    expect(queries?.retry).toBe(shouldRetryQuery);
    expect(mutations?.retry).toBe(false);
  });

  it('defines stale times per data class', () => {
    expect(STALE_TIME).toEqual({
      meta: 60 * 60_000,
      analytics: 5 * 60_000,
      videoDetail: 10 * 60_000,
      modelInfo: Infinity,
      session: 5 * 60_000,
      members: 30_000,
    });
  });

  it('creates independent clients', () => {
    expect(createQueryClient()).not.toBe(createQueryClient());
  });
});

describe('retry policy', () => {
  it.each([
    [0, apiError(503, 'database_unavailable'), true],
    [0, apiError(504, 'query_timeout'), true],
    [0, ApiError.network('r'), true],
    [0, ApiError.timeout(100, 'r'), true],
    [1, apiError(503, 'database_unavailable'), false],
    [0, apiError(422, 'invalid_filter'), false],
    [0, apiError(404, 'not_found'), false],
    [0, apiError(500, 'internal_error'), false],
    [0, new Error('render bug'), false],
  ])('failureCount=%i %o -> retry %s', (failureCount, error, expected) => {
    expect(shouldRetryQuery(failureCount, error)).toBe(expected);
  });

  it('backs off exponentially with a cap', () => {
    expect([0, 1, 2, 3, 10].map(retryDelay)).toEqual([1000, 2000, 4000, 8000, 8000]);
  });
});

describe('QueryClient with the API client (MSW)', () => {
  const KPIS_URL = `${config.apiBaseUrl}/api/v1/overview/kpis`;
  const fetchKpis = (client: ReturnType<typeof createQueryClient>) =>
    client.fetchQuery({
      queryKey: queryKeys.overview.kpis(),
      queryFn: ({ signal }) =>
        callApi((init) => apiClient.GET('/api/v1/overview/kpis', init), { signal }),
      retryDelay: 0,
    });

  it('retries a transient 503 once and then succeeds', async () => {
    let calls = 0;
    server.use(
      http.get(KPIS_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              { error: { code: 'database_unavailable', message: 'down', request_id: 'r' } },
              { status: 503 },
            )
          : HttpResponse.json({ filters: {}, data: { ok: true } });
      }),
    );
    await expect(fetchKpis(createQueryClient())).resolves.toMatchObject({ data: { ok: true } });
    expect(calls).toBe(2);
  });

  it('does not retry validation errors', async () => {
    let calls = 0;
    server.use(
      http.get(KPIS_URL, () => {
        calls += 1;
        return HttpResponse.json(
          {
            error: { code: 'invalid_filter', message: 'bad', field: 'countries', request_id: 'r' },
          },
          { status: 422 },
        );
      }),
    );
    await expect(fetchKpis(createQueryClient())).rejects.toMatchObject({ code: 'invalid_filter' });
    expect(calls).toBe(1);
  });

  it('marks the user signed out when a data request finds the session gone (no retry)', async () => {
    let calls = 0;
    server.use(
      http.get(KPIS_URL, () => {
        calls += 1;
        return HttpResponse.json(
          { error: { code: 'not_authenticated', message: 'Authentication required.' } },
          { status: 401 },
        );
      }),
    );
    const client = createQueryClient();
    client.setQueryData(queryKeys.auth.me(), { user: { id: 'u' } });
    await expect(fetchKpis(client)).rejects.toMatchObject({ status: 401 });
    expect(calls).toBe(1);
    expect(client.getQueryData(queryKeys.auth.me())).toBeNull();
  });

  it('keeps the session on other errors, including 403', async () => {
    server.use(
      http.get(KPIS_URL, () =>
        HttpResponse.json({ error: { code: 'forbidden', message: 'No.' } }, { status: 403 }),
      ),
    );
    const client = createQueryClient();
    const user = { user: { id: 'u' } };
    client.setQueryData(queryKeys.auth.me(), user);
    await expect(fetchKpis(client)).rejects.toMatchObject({ code: 'forbidden' });
    expect(client.getQueryData(queryKeys.auth.me())).toBe(user);
  });
});
