import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { DayCount } from '../components/YearGrid'

export type PostAuthor = {
  handle: string | null
  display_name: string | null
  username: string
  avatar_path: string | null
}

export type PostTitle = {
  tmdb_id: number
  type: string
  name: string
  poster_path: string | null
  year: number | null
}

export type Post = {
  id: string
  body: string
  spoiler: boolean
  created_at: string
  edited_at: string | null
  author: PostAuthor
  likes: number
  you_liked: boolean
  yours: boolean
  title: PostTitle | null
  shared: Post | null
  replies: Post[]
  reply_count: number
}

export type PostsPage = { total: number; comments: Post[]; hidden?: boolean }

/** The name to show. A handle is what people choose, so it wins. */
export function nameOf(author: PostAuthor): string {
  return author.display_name || (author.handle ? `@${author.handle}` : author.username)
}

/** Where clicking a person goes. Null when they never picked a handle. */
export function profileHref(author: PostAuthor): string | null {
  return author.handle ? `/app/u/${author.handle}` : null
}

export function useFeed() {
  return useQuery({
    queryKey: ['feed'],
    queryFn: () => api.get<PostsPage>('/api/feed'),
    staleTime: 30_000,
  })
}

export function useTitleComments(type: string, tmdbId: number) {
  return useQuery({
    queryKey: ['comments', type, tmdbId],
    queryFn: () => api.get<PostsPage>(`/api/titles/${type}/${tmdbId}/comments`),
    staleTime: 30_000,
  })
}

/* Every mutation refreshes the feed, the profile and the title thread,
   because the same post appears in all three and a stale copy in one of
   them is how a like appears to have been lost. */
function useRefresh() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['feed'] })
    queryClient.invalidateQueries({ queryKey: ['comments'] })
    queryClient.invalidateQueries({ queryKey: ['profile-posts'] })
  }
}

export function useWritePost() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (payload: {
      body: string
      spoiler?: boolean
      type?: string
      tmdb_id?: number
      shares?: string
      reply_to?: string
    }) => api.post<Post>('/api/posts', payload),
    onSuccess: refresh,
  })
}

export function useWriteComment(type: string, tmdbId: number) {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (payload: { body: string; spoiler: boolean }) =>
      api.post<Post>(`/api/titles/${type}/${tmdbId}/comments`, payload),
    onSuccess: refresh,
  })
}

export function useLikePost() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => api.post<Post>(`/api/comments/${id}/like`),
    onSuccess: refresh,
  })
}

export function useDeletePost() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/comments/${id}`),
    onSuccess: refresh,
  })
}

export type Profile = {
  handle: string | null
  username: string
  display_name: string | null
  avatar_path: string | null
  visibility: string
  yours: boolean
  friend_status: string | null
  joined: string | null
  watched?: number | null
  hours?: number | null
  loved?: number | null
  genres?: { name: string; count: number }[] | null
  favourites?: PostTitle[] | null
  lists?: { id: string; name: string; kind: string; count: number }[] | null
  featured_line?: {
    id: string
    body: string
    character: string | null
    title: {
      tmdb_id: number
      type: string
      name: string
      backdrop_path: string | null
      poster_path: string | null
      year: number | null
    }
  } | null
  days?: DayCount[] | null
  years?: number[] | null
  streak?: number | null
  avg_rating?: number | null
  hidden: string[]
}

export function useProfile(handle: string) {
  return useQuery({
    queryKey: ['profile', handle],
    queryFn: () => api.get<Profile>(`/api/profiles/${handle}`),
    retry: false,
  })
}

export function useProfilePosts(handle: string) {
  return useQuery({
    queryKey: ['profile-posts', handle],
    queryFn: () => api.get<PostsPage>(`/api/profiles/${handle}/posts`),
    retry: false,
  })
}

export function usePeopleSearch(term: string) {
  return useQuery({
    queryKey: ['people-search', term],
    queryFn: () => api.get<PostAuthor[]>(`/api/profiles?q=${encodeURIComponent(term)}`),
    enabled: term.trim().length >= 1,
    staleTime: 60_000,
  })
}
