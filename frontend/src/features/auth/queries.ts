import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient, callApi } from '../../api/client';
import type { CurrentUser, LoginRequest, RegisterRequest } from '../../api/types';
import { isSessionLost, queryKeys, STALE_TIME } from '../../query';

/**
 * The signed-in user, or null when there is no valid session. The session itself is an
 * HttpOnly cookie that JavaScript never sees; this only mirrors what the server reports.
 */
export function useCurrentUser() {
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: async ({ signal }): Promise<CurrentUser | null> => {
      try {
        const response = await callApi((init) => apiClient.GET('/api/v1/auth/me', init), {
          signal,
        });
        return response.data;
      } catch (error) {
        if (isSessionLost(error)) return null;
        throw error;
      }
    },
    staleTime: STALE_TIME.session,
  });
}

/** A new identity: drop everything cached for the previous one, then store the new user. */
function useStartSession() {
  const queryClient = useQueryClient();
  return (user: CurrentUser) => {
    queryClient.removeQueries();
    queryClient.setQueryData(queryKeys.auth.me(), user);
  };
}

export function useLogin() {
  const startSession = useStartSession();
  return useMutation({
    mutationFn: (body: LoginRequest) =>
      callApi((init) => apiClient.POST('/api/v1/auth/login', { body, ...init })),
    onSuccess: (response) => startSession(response.data),
  });
}

export function useRegister() {
  const startSession = useStartSession();
  return useMutation({
    mutationFn: (body: RegisterRequest) =>
      callApi((init) => apiClient.POST('/api/v1/auth/register', { body, ...init })),
    onSuccess: (response) => startSession(response.data),
  });
}

/** Revokes the session on the server, then forgets every cached response locally. */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => callApi((init) => apiClient.POST('/api/v1/auth/logout', init)),
    onSettled: () => {
      queryClient.removeQueries();
      queryClient.setQueryData(queryKeys.auth.me(), null);
    },
  });
}
