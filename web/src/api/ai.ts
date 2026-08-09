import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { TitleCard } from './catalog'

// No model name here on purpose. Which model answers is an operator setting
// that changes without notice; it lives in Admin, AI settings.
export type AIStatus = {
  enabled: boolean
  embedded_titles: number
}

export type NLSearchResult = {
  parsed: {
    mood?: string
    genres?: string[]
    types?: string[]
    runtime_max?: number | null
    year_from?: number | null
    year_to?: number | null
    on_shared_services?: boolean
  }
  results: TitleCard[]
}

export type AISettings = {
  enabled: boolean
  base_url: string
  chat_model: string
  embed_model: string
  has_api_key: boolean
}

export function useAIStatus() {
  return useQuery({
    queryKey: ['ai-status'],
    queryFn: () => api.get<AIStatus>('/api/ai/status'),
    staleTime: 60_000,
  })
}

export function useNLSearch() {
  return useMutation({
    mutationFn: (q: string) => api.post<NLSearchResult>('/api/ai/search', { q }),
  })
}

export function useSimilar(type: string, tmdbId: number) {
  return useQuery({
    queryKey: ['similar', type, tmdbId],
    queryFn: () => api.get<{ results: TitleCard[] }>(`/api/titles/${type}/${tmdbId}/similar`),
    staleTime: 10 * 60_000,
  })
}

export function useVibeTags(type: string, tmdbId: number) {
  return useQuery({
    queryKey: ['tags', type, tmdbId],
    queryFn: () => api.get<{ tags: { tag: string; score: number }[] }>(
      `/api/titles/${type}/${tmdbId}/tags`,
    ),
    staleTime: 60 * 60_000,
  })
}

export function useAISettings() {
  return useQuery({
    queryKey: ['ai-settings'],
    queryFn: () => api.get<AISettings>('/api/admin/settings/ai'),
  })
}
