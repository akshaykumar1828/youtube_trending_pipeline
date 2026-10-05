import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

import { isApiError, isRetryableError } from '../api/errors';
import { queryKeys } from './queryKeys';

const MINUTE = 60_000;

/**
 * Stale times per data class. The backend data only changes when the materialized
 * views are refreshed, so data stays fresh for minutes, not seconds.
 */
export const STALE_TIME = {
  meta: 60 * MINUTE,
  analytics: 5 * MINUTE,
  videoDetail: 10 * MINUTE,
  modelInfo: Infinity,
  /** The server re-checks the session on every API call; this only limits /auth/me polling. */
  session: 5 * MINUTE,
  members: 30_000,
} as const;

export const GC_TIME = 30 * MINUTE;
export const MAX_QUERY_RETRIES = 1;

/** One retry for transient failures (503, 504, network, timeout); never for 4xx or other errors. */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  return failureCount < MAX_QUERY_RETRIES && isRetryableError(error);
}

export function retryDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 8000);
}

/** The session ended (expired, revoked, signed out elsewhere): the API answered 401. */
export function isSessionLost(error: unknown): boolean {
  return isApiError(error) && error.status === 401 && error.code === 'not_authenticated';
}

/**
 * When any query or mutation finds the session gone, mark the user signed out; the route guard
 * then redirects to the sign-in page. (Failed sign-in attempts are `invalid_credentials`, not this.)
 */
export function createQueryClient(): QueryClient {
  const onSessionLost = (error: unknown) => {
    if (isSessionLost(error)) client.setQueryData(queryKeys.auth.me(), null);
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: onSessionLost }),
    mutationCache: new MutationCache({ onError: onSessionLost }),
    defaultOptions: {
      queries: {
        staleTime: STALE_TIME.analytics,
        gcTime: GC_TIME,
        refetchOnWindowFocus: false,
        retry: shouldRetryQuery,
        retryDelay,
      },
      mutations: {
        retry: false,
      },
    },
  });
  return client;
}
