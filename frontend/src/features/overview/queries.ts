import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { apiClient, callApi } from '../../api/client';
import type { DailyVolumeParams, FilterParams } from '../../api/types';
import { normalizeFilters, queryKeys } from '../../query';

export function useKpis(filters: FilterParams) {
  return useQuery({
    queryKey: queryKeys.overview.kpis(filters),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/overview/kpis', {
            params: { query: normalizeFilters(filters) },
            ...init,
          }),
        { signal },
      ),
    placeholderData: keepPreviousData,
  });
}

export function useDailyVolume(filters: FilterParams, params: DailyVolumeParams = {}) {
  return useQuery({
    queryKey: queryKeys.overview.dailyVolume(filters, params),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/overview/daily-volume', {
            params: { query: { ...normalizeFilters(filters), ...params } },
            ...init,
          }),
        { signal },
      ),
    placeholderData: keepPreviousData,
  });
}
