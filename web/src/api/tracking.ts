import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { TitleCard } from './catalog'

export type ListSummary = {
  id: string
  name: string
  // 'cinema' is created by the tracker and filtered out server side, but
  // the type admits it so nothing narrows it away by accident.
  kind: 'watchlist' | 'custom' | 'shared' | 'cinema'
  count: number
  posters: string[]
}

export type ListItemOut = {
  title: TitleCard
  note: string | null
  added_by: string | null
  added_at: string
}

export type ListDetail = {
  id: string
  name: string
  kind: string
  items: ListItemOut[]
}

export type WatchEventOut = {
  id: string
  title: TitleCard
  watched_at: string
  rating_10: number | null
  loved: boolean
  source: string
}

export type TitleState = {
  lists: string[]
  watched_count: number
  my_rating: number | null
  loved: boolean
}

export type ProviderOption = {
  provider_id: number
  provider_name: string
  logo_path: string | null
}

export function useLists() {
  return useQuery({
    queryKey: ['lists'],
    queryFn: () => api.get<{ lists: ListSummary[] }>('/api/lists'),
  })
}

export function useListItems(listId: string | undefined) {
  return useQuery({
    queryKey: ['list', listId],
    queryFn: () => api.get<ListDetail>(`/api/lists/${listId}/items`),
    enabled: !!listId,
  })
}

const HISTORY_PAGE = 50

export function useHistory() {
  return useInfiniteQuery({
    queryKey: ['history'],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.get<{ total: number; events: WatchEventOut[] }>(
        `/api/history?limit=${HISTORY_PAGE}&offset=${pageParam}`,
      ),
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + page.events.length, 0)
      return loaded < lastPage.total ? loaded : undefined
    },
  })
}

export function useTitleState(type: string, tmdbId: number) {
  return useQuery({
    queryKey: ['state', type, tmdbId],
    queryFn: () => api.get<TitleState>(`/api/titles/${type}/${tmdbId}/state`),
  })
}

export function useProviders(country: string | null) {
  return useQuery({
    queryKey: ['providers', country],
    queryFn: () => api.get<ProviderOption[]>(`/api/providers?country=${country}`),
    enabled: !!country && country.length === 2,
    staleTime: 24 * 60 * 60_000,
    retry: false,
  })
}

function useInvalidate() {
  const queryClient = useQueryClient()
  return (keys: unknown[][]) => {
    keys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }))
    // Home follows what you save and watch, but only refreshes on your next
    // visit so the page never moves while you are using it.
    queryClient.invalidateQueries({ queryKey: ['home'], refetchType: 'none' })
  }
}

export function useCreateList() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (name: string) => api.post<ListSummary>('/api/lists', { name }),
    onSuccess: () => invalidate([['lists']]),
  })
}

export function useDeleteList() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (listId: string) => api.delete(`/api/lists/${listId}`),
    onSuccess: () => invalidate([['lists']]),
  })
}

export function useAddToList(type: string, tmdbId: number) {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (payload: { listId: string; note?: string }) =>
      api.post(`/api/lists/${payload.listId}/items`, { type, tmdb_id: tmdbId, note: payload.note }),
    onSuccess: (_data, vars) =>
      invalidate([['lists'], ['list', vars.listId], ['state', type, tmdbId]]),
  })
}

export function useRemoveFromList(type: string, tmdbId: number) {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (listId: string) => api.delete(`/api/lists/${listId}/items/${type}/${tmdbId}`),
    onSuccess: (_data, listId) => invalidate([['lists'], ['list', listId], ['state', type, tmdbId]]),
  })
}

export function useMarkWatched(type: string, tmdbId: number) {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (payload: { rating_10?: number; loved?: boolean }) =>
      api.post<WatchEventOut>('/api/history', { type, tmdb_id: tmdbId, ...payload }),
    onSuccess: () => invalidate([['history'], ['state', type, tmdbId]]),
  })
}

export function useUpdateEvent() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (payload: { id: string; rating_10?: number; loved?: boolean }) =>
      api.patch<WatchEventOut>(`/api/history/${payload.id}`, {
        rating_10: payload.rating_10,
        loved: payload.loved,
      }),
    onSuccess: () => invalidate([['history']]),
  })
}

export function useDeleteEvent() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/history/${id}`),
    onSuccess: () => invalidate([['history']]),
  })
}

export function useUpdateProfile() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (payload: {
      country_code?: string
      services?: number[]
      languages?: string[]
      genres?: number[]
      parents_guide?: boolean
      discovery?: string
      hide_watched?: boolean
      /** A word when a paid service goes a month unused. Opt-in. */
      expense_alerts?: boolean
      /** Suggest only what is on a service they subscribe to. */
      only_my_services?: boolean
      default_type?: string
      notify_kinds?: string[]
      reduce_motion?: boolean
      countries?: string[]
      handle?: string
      display_name?: string
      visibility?: string
      panel_visibility?: Record<string, string>
      email_alerts?: boolean
    }) => api.put('/api/me', payload),
    onSuccess: () => invalidate([['me']]),
  })
}
