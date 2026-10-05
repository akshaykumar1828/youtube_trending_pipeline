import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { apiClient, callApi } from '../../api/client';
import type { FilterParams, VideoListParams } from '../../api/types';
import { normalizeFilters, queryKeys, STALE_TIME } from '../../query';

/** One server-side page of videos; the backend filters, sorts and paginates. */
export function useVideoList(filters: FilterParams, params: VideoListParams) {
  return useQuery({
    queryKey: queryKeys.videos.list(filters, params),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/videos', {
            params: { query: { ...normalizeFilters(filters), ...params } },
            ...init,
          }),
        { signal },
      ),
    placeholderData: keepPreviousData,
  });
}

export function useVideo(videoId: string) {
  return useQuery({
    queryKey: queryKeys.videos.detail(videoId),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/videos/{video_id}', {
            params: { path: { video_id: videoId } },
            ...init,
          }),
        { signal },
      ),
    staleTime: STALE_TIME.videoDetail,
    select: (response) => response.data,
  });
}

/** Full, unfiltered trending history of one video (all countries and dates). */
export function useVideoHistory(videoId: string) {
  return useQuery({
    queryKey: queryKeys.videos.history(videoId),
    queryFn: ({ signal }) =>
      callApi(
        (init) =>
          apiClient.GET('/api/v1/videos/{video_id}/history', {
            params: { path: { video_id: videoId } },
            ...init,
          }),
        { signal },
      ),
    staleTime: STALE_TIME.videoDetail,
    select: (response) => response.data,
  });
}
