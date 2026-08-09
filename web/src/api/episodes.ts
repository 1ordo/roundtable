import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

export type EpisodeOut = {
  id: string
  season: number
  episode: number
  name: string | null
  overview: string | null
  air_date: string | null
  runtime: number | null
  still_path: string | null
  // Whether it has actually gone out. An episode that has not aired can be
  // shown but never ticked off, so the two states have to be distinct.
  aired: boolean
  watched: boolean
}

export type SeasonOut = {
  season: number
  episodes: EpisodeOut[]
}

export type ShowEpisodes = {
  seasons: SeasonOut[]
  next_up: EpisodeOut | null
  aired: number
  watched: number
  upcoming: number
  complete: boolean
}

export function useEpisodes(tmdbId: number, enabled = true) {
  return useQuery({
    queryKey: ['episodes', tmdbId],
    queryFn: () => api.get<ShowEpisodes>(`/api/titles/tv/${tmdbId}/episodes`),
    enabled,
  })
}

export function useMarkEpisode(tmdbId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { season: number; episode: number; watched: boolean }) =>
      api.post<ShowEpisodes>(`/api/titles/tv/${tmdbId}/episodes/watched`, body),
    onSuccess: (data) => {
      // The endpoint answers with the whole show, so the grid, the counts
      // and next-up all move together rather than in three refetches.
      qc.setQueryData(['episodes', tmdbId], data)
      qc.invalidateQueries({ queryKey: ['title-state'] })
      qc.invalidateQueries({ queryKey: ['history'] })
    },
  })
}

export function useMarkSeason(tmdbId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { season: number; watched: boolean }) =>
      api.post<ShowEpisodes>(`/api/titles/tv/${tmdbId}/episodes/season`, body),
    onSuccess: (data) => {
      qc.setQueryData(['episodes', tmdbId], data)
      qc.invalidateQueries({ queryKey: ['title-state'] })
      qc.invalidateQueries({ queryKey: ['history'] })
    },
  })
}
