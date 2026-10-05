import createClient from 'openapi-fetch';

import { config } from '../config';
import { ApiError, normalizeErrorResponse, REQUEST_ID_HEADER } from './errors';
import type { paths } from './generated/schema';

export const DEFAULT_TIMEOUT_MS = 20_000; // backend statement timeout is 15 s
export const PREDICTION_TIMEOUT_MS = 30_000;

/**
 * Typed openapi-fetch client for the FastAPI contract (paths/params/bodies checked at compile time).
 * Arrays are serialized as repeated keys (?country=IN&country=US), which is what FastAPI expects.
 *
 * `fetch` is resolved when each request is made, not when the client is created: openapi-fetch
 * otherwise captures globalThis.fetch at import time, which would bypass fetch interception
 * installed later (MSW in tests, instrumentation in the browser).
 *
 * `credentials: 'include'` sends the HttpOnly session cookie to the API origin. The cookie is
 * never readable from JavaScript; the backend allows credentials only for allowlisted origins.
 */
export function createApiClient(baseUrl: string = config.apiBaseUrl) {
  return createClient<paths>({
    baseUrl,
    credentials: 'include',
    fetch: (request: Request) => globalThis.fetch(request),
    querySerializer: { array: { style: 'form', explode: true } },
  });
}

export type ApiClient = ReturnType<typeof createApiClient>;

export const apiClient: ApiClient = createApiClient();

/** 32 hex characters; uses getRandomValues so it also works outside secure contexts. */
export function generateRequestId(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Per-request options that callApi passes to the openapi-fetch call.
 * A type alias (not an interface) so it is assignable to openapi-fetch's indexed options type.
 */
export type RequestInitParts = {
  signal: AbortSignal;
  headers: Record<string, string>;
};

export interface CallApiOptions {
  /** Caller cancellation (e.g. TanStack Query's signal). Cancellation is re-thrown, not an ApiError. */
  signal?: AbortSignal;
  timeoutMs?: number;
}

type FetchResult = { data?: unknown; error?: unknown; response: Response };

/**
 * Runs one typed API call and returns its success body, or throws ApiError.
 *
 *   const body = await callApi((init) =>
 *     apiClient.GET('/api/v1/overview/kpis', { params: { query: { country: ['IN'] } }, ...init }),
 *   );
 *
 * Adds a fresh X-Request-ID header, enforces a timeout, and normalizes every failure
 * (backend error envelope, other HTTP errors, network failure, timeout) into ApiError.
 */
export async function callApi<R extends FetchResult>(
  perform: (init: RequestInitParts) => Promise<R>,
  { signal, timeoutMs = DEFAULT_TIMEOUT_MS }: CallApiOptions = {},
): Promise<NonNullable<R['data']>> {
  const requestId = generateRequestId();
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

  let result: R;
  try {
    result = await perform({ signal: combined, headers: { [REQUEST_ID_HEADER]: requestId } });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    if (timeout.aborted) throw ApiError.timeout(timeoutMs, requestId, cause);
    throw ApiError.network(requestId, cause);
  }

  const { data, error, response } = result;
  if (response.ok && data !== undefined && data !== null) {
    return data as NonNullable<R['data']>;
  }
  throw normalizeErrorResponse(response, error, requestId);
}
