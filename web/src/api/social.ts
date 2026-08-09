import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

export type Person = {
  id: string
  username: string
  handle: string | null
  display_name: string | null
  avatar_path: string | null
  visibility: string
  relation: 'none' | 'pending_out' | 'pending_in' | 'friends'
}

export type FriendsPage = {
  friends: Person[]
  incoming: Person[]
  outgoing: Person[]
}

export type NightPick = {
  tmdb_id: number
  type: string
  name: string
  poster_path: string | null
  year: number | null
  suggested_by: string
  votes: number
  you_voted: boolean
}

export type Night = {
  id: string
  name: string
  host: string
  status: 'planning' | 'watched' | 'cancelled'
  scheduled_for: string | null
  survey_after_hours: number
  members: { username: string; avatar_path: string | null; status: string }[]
  queue: NightPick[]
  watched: NightPick | null
  watched_at: string | null
  your_status: string
  you_host: boolean
  awaiting_your_verdict: boolean
}

export function useFriends() {
  return useQuery({
    queryKey: ['friends'],
    queryFn: () => api.get<FriendsPage>('/api/friends'),
    staleTime: 30_000,
  })
}

export function usePeopleSearch(term: string) {
  return useQuery({
    queryKey: ['people-search', term],
    queryFn: () => api.get<Person[]>(`/api/users/search?q=${encodeURIComponent(term)}`),
    enabled: term.trim().length >= 2,
    staleTime: 30_000,
  })
}

/* Every friendship action invalidates the same two queries, because the
   relation shown on a search result and the lists on the friends page are
   two views of one fact. */
function useFriendAction<T>(call: (input: T) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['friends'] })
      queryClient.invalidateQueries({ queryKey: ['people-search'] })
    },
  })
}

export function useAddFriend() {
  return useFriendAction((username: string) =>
    api.post('/api/friends/request', { username }),
  )
}

export function useAcceptFriend() {
  return useFriendAction((username: string) =>
    api.post(`/api/friends/${encodeURIComponent(username)}/accept`, {}),
  )
}

export function useRemoveFriend() {
  return useFriendAction((username: string) =>
    api.delete(`/api/friends/${encodeURIComponent(username)}`),
  )
}

export function useNights() {
  return useQuery({
    queryKey: ['nights'],
    queryFn: () => api.get<Night[]>('/api/nights'),
    staleTime: 15_000,
  })
}

function useNightAction<T>(call: (input: T) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nights'] })
      // A settled night writes to everyone's history.
      queryClient.invalidateQueries({ queryKey: ['history'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })
}

export function useCreateNight() {
  return useNightAction(
    (body: {
      name: string
      invite: string[]
      scheduled_for?: string | null
      survey_after_hours: number
    }) => api.post<Night>('/api/nights', body),
  )
}

export function useReplyToNight() {
  return useNightAction(({ id, coming }: { id: string; coming: boolean }) =>
    api.post<Night>(`/api/nights/${id}/reply?coming=${coming}`, {}),
  )
}

export function useQueueTitle() {
  return useNightAction(({ id, type, tmdb_id }: { id: string; type: string; tmdb_id: number }) =>
    api.post<Night>(`/api/nights/${id}/queue`, { type, tmdb_id }),
  )
}

export function useVotePick() {
  return useNightAction(({ id, type, tmdb_id }: { id: string; type: string; tmdb_id: number }) =>
    api.post<Night>(`/api/nights/${id}/vote`, { type, tmdb_id }),
  )
}

export function useRemovePick() {
  return useNightAction(({ id, type, tmdb_id }: { id: string; type: string; tmdb_id: number }) =>
    api.delete<Night>(`/api/nights/${id}/queue?type=${type}&tmdb_id=${tmdb_id}`),
  )
}

export function useMarkWatched() {
  return useNightAction(({ id, type, tmdb_id }: { id: string; type: string; tmdb_id: number }) =>
    api.post<Night>(`/api/nights/${id}/watched`, { type, tmdb_id }),
  )
}

export function useGiveVerdict() {
  return useNightAction(
    ({
      id,
      ...body
    }: {
      id: string
      rating_10: number | null
      loved: boolean
      note: string | null
    }) => api.post<Night>(`/api/nights/${id}/verdict`, body),
  )
}
