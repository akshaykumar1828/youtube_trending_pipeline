import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient, callApi } from '../../api/client';
import type { CreateMemberRequest, UpdateMemberRequest } from '../../api/types';
import { queryKeys, STALE_TIME } from '../../query';

/** Members of the caller's workspace. The server scopes this to the session's tenant. */
export function useMembers() {
  return useQuery({
    queryKey: queryKeys.tenant.members(),
    queryFn: ({ signal }) =>
      callApi((init) => apiClient.GET('/api/v1/tenant/members', init), { signal }),
    staleTime: STALE_TIME.members,
    select: (response) => response.data,
  });
}

export function useCreateMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateMemberRequest) =>
      callApi((init) => apiClient.POST('/api/v1/tenant/members', { body, ...init })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.tenant.all }),
  });
}

export function useUpdateMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, body }: { userId: string; body: UpdateMemberRequest }) =>
      callApi((init) =>
        apiClient.PATCH('/api/v1/tenant/members/{user_id}', {
          params: { path: { user_id: userId } },
          body,
          ...init,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.tenant.all }),
  });
}
