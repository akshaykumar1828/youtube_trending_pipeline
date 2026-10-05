import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { apiClient, callApi } from '../../api/client';
import type { ChannelParams, EngagementParams, FilterParams } from '../../api/types';
import { normalizeFilters, queryKeys } from '../../query';

export function useCategoryPerformance(filters: FilterParams) {
  return useQuery({
    queryKey: queryKeys.analytics.categories(filters),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/analytics/categories', {
            params: { query: normalizeFilters(filters) },
            ...init,
          }),
        { signal },
      ),
    placeholderData: keepPreviousData,
  });
}

export function useCountryPerformance(filters: FilterParams) {
  return useQuery({
    queryKey: queryKeys.analytics.countries(filters),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/analytics/countries', {
            params: { query: normalizeFilters(filters) },
            ...init,
          }),
        { signal },
      ),
    placeholderData: keepPreviousData,
  });
}

export function useEngagementAnalysis(filters: FilterParams, params: EngagementParams = {}) {
  return useQuery({
    queryKey: queryKeys.analytics.engagement(filters, params),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/analytics/engagement', {
            params: { query: { ...normalizeFilters(filters), ...params } },
            ...init,
          }),
        { signal },
      ),
    placeholderData: keepPreviousData,
  });
}

export function useTopChannels(filters: FilterParams, params: ChannelParams = {}) {
  return useQuery({
    queryKey: queryKeys.analytics.channels(filters, params),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/analytics/channels', {
            params: { query: { ...normalizeFilters(filters), ...params } },
            ...init,
          }),
        { signal },
      ),
    placeholderData: keepPreviousData,
  });
}
