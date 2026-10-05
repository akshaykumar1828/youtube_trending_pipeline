import { useMutation, useQuery } from '@tanstack/react-query';

import { apiClient, callApi, PREDICTION_TIMEOUT_MS } from '../../api/client';
import type { PredictionRequest } from '../../api/types';
import { queryKeys, STALE_TIME } from '../../query';

/** Model card: label definition, supported inputs, limitations (static for the session). */
export function useModelInfo() {
  return useQuery({
    queryKey: queryKeys.predictions.modelInfo(),
    queryFn: ({ signal }) =>
      callApi((init) => apiClient.GET('/api/v1/predictions/model-info', init), { signal }),
    staleTime: STALE_TIME.modelInfo,
    select: (response) => response.data,
  });
}

/** Scores one video. A mutation: it only runs when the user submits the form. */
export function usePrediction() {
  return useMutation({
    mutationFn: (body: PredictionRequest) =>
      callApi((init) => apiClient.POST('/api/v1/predictions', { body, ...init }), {
        timeoutMs: PREDICTION_TIMEOUT_MS,
      }),
  });
}
