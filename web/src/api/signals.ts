import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { TitleCard } from './catalog'
import type { HomeRow } from './catalog'

export type SignalState = { liked: boolean; disliked: boolean }

export function useSignalState(type: string, tmdbId: number) {
  return useQuery({
    queryKey: ['signal', type, tmdbId],
    queryFn: () => api.get<SignalState>(`/api/titles/${type}/${tmdbId}/signal`),
  })
}

export function useSendSignal(type: string, tmdbId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (kind: 'view' | 'click_out' | 'like' | 'dislike') =>
      api.post<SignalState>(`/api/titles/${type}/${tmdbId}/signal`, { kind }),
    onSuccess: (state, kind) => {
      if (kind === 'like' || kind === 'dislike') {
        queryClient.setQueryData(['signal', type, tmdbId], state)
      }
      // Views and click-outs teach the algorithm too, so let home know it is
      // out of date. It refetches when the person next opens it, never
      // under their hands.
      queryClient.invalidateQueries({ queryKey: ['home'], refetchType: 'none' })
      queryClient.invalidateQueries({ queryKey: ['new'], refetchType: 'none' })
    },
  })
}

export type Person = { username: string; avatar_path: string | null; is_me: boolean }

export function usePeople() {
  return useQuery({ queryKey: ['people'], queryFn: () => api.get<Person[]>('/api/people') })
}

export type GroupOut = { id: string; name: string; members: string[]; created_by: string }

export function useGroups() {
  return useQuery({ queryKey: ['groups'], queryFn: () => api.get<GroupOut[]>('/api/groups') })
}

export function useCreateGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { name: string; member_usernames: string[] }) =>
      api.post<GroupOut>('/api/groups', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['groups'] }),
  })
}

export function useDeleteGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/groups/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['groups'] }),
  })
}

export function useGroupSuggestions() {
  return useMutation({
    mutationFn: (input: { groupId: string; weights?: Record<string, number> }) =>
      api.post<{ results: TitleCard[]; without_taste: string[] }>(
        `/api/groups/${input.groupId}/suggestions`,
        { weights: input.weights },
      ),
  })
}

export function useNew() {
  return useQuery({
    queryKey: ['new'],
    queryFn: () => api.get<{ rows: HomeRow[] }>('/api/new'),
    staleTime: 10 * 60_000,
    retry: false,
  })
}
