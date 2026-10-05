import { useQuery } from '@tanstack/react-query';

import { apiClient, callApi } from '../../api/client';
import { queryKeys, STALE_TIME } from '../../query';

/** Countries, categories, date range and default window — all from the backend. */
export function useFilterOptions() {
  return useQuery({
    queryKey: queryKeys.meta.filters(),
    queryFn: ({ signal }) =>
      callApi((init) => apiClient.GET('/api/v1/meta/filters', init), { signal }),
    staleTime: STALE_TIME.meta,
    select: (response) => response.data,
  });
}
