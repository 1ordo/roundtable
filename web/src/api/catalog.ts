import { useQuery } from '@tanstack/react-query'
import { api, ApiError } from './client'

export type TitleCard = {
  tmdb_id: number
  type: 'movie' | 'tv'
  name: string
  poster_path: string | null
  backdrop_path: string | null
  year: number | null
  tmdb_rating: number | null
  /** 0-100 fit for the signed-in person, absent until there is enough signal. */
  match?: number | null
  /** Age rating, present only when the viewer turned the parents guide on. */
  certification?: string | null
}

export type HomeRow = { key: string; title: string; items: TitleCard[] }

export type CastMember = {
  name: string
  character: string | null
  profile_path: string | null
  /** TMDB person id, so every face links to their own page. */
  person_id?: number | null
}

export type ProviderEntry = {
  provider_name: string
  logo_path: string | null
  kind: 'stream' | 'rent' | 'buy' | 'ads' | 'free'
  url: string | null
  /** A service you subscribe to that the catalogue does not track in your
      country, carrying this somewhere else. Shown because a gap in the data
      is not proof you cannot watch it, marked because it is not a local
      listing either. */
  unlisted_locally?: boolean
}

export type TitleDetail = {
  id: string
  tmdb_id: number
  type: 'movie' | 'tv'
  name: string
  original_name: string | null
  year: number | null
  overview: string | null
  original_language: string | null
  runtime: number | null
  genres: { id: number; name: string }[]
  keywords: string[]
  poster_path: string | null
  backdrop_path: string | null
  tmdb_rating: number | null
  tmdb_votes: number | null
  imdb_rating: number | null
  rt_score: number | null
  metacritic: number | null
  trailer_youtube_key: string | null
  cast: CastMember[]
  availability: Record<string, ProviderEntry[]>
  countries: string[]
  director?: string | null
  country?: string | null
  rated?: string | null
  awards?: string | null
  imdb_id?: string | null
  match?: number | null
  /** Official age ratings by country, straight from the provider. */
  certifications?: Record<string, string>
  /** The one that applies to this viewer's country. */
  certification?: string | null
  collection_id?: number | null
  collection_name?: string | null
}

export type PersonResult = {
  person_id: number
  name: string
  profile_path: string | null
  known_for: string
  you_follow: boolean
}

export type PagedResults = {
  results: TitleCard[]
  page: number
  total_pages: number
  // Search answers with both kinds of thing; browse only ever has titles.
  people?: PersonResult[]
}

const IMG_BASE = 'https://image.tmdb.org/t/p'

export function img(path: string | null, size: 'w185' | 'w342' | 'w500' | 'w1280'): string | null {
  if (!path) return null
  // OMDb returns absolute poster URLs; TMDB returns a path to size-prefix.
  if (path.startsWith('http')) return path
  return `${IMG_BASE}/${size}${path}`
}

export function isNotConfigured(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503
}

/** Read the home page as it is built: one row per newline-delimited JSON
 * line. Warm cache arrives as one burst; a cold build trickles in, which
 * is the whole point — the first shelf is on screen while the last is
 * still being computed. */
export async function streamHome(
  onRow: (row: HomeRow) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch('/api/home/stream', {
    signal,
    headers: { Accept: 'application/x-ndjson' },
  })
  if (!resp.ok || !resp.body) {
    throw new ApiError(resp.status, 'could not load the home page')
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let newline = buffer.indexOf('\n')
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim()
      buffer = buffer.slice(newline + 1)
      if (line) onRow(JSON.parse(line) as HomeRow)
      newline = buffer.indexOf('\n')
    }
  }
  const rest = buffer.trim()
  if (rest) onRow(JSON.parse(rest) as HomeRow)
}

export function useHome(enabled = true) {
  return useQuery({
    queryKey: ['home'],
    queryFn: () => api.get<{ rows: HomeRow[] }>('/api/home'),
    // What you do marks this stale, and it refreshes the next time you come
    // back to the page. Nothing rearranges itself while you are reading it.
    staleTime: 10 * 60_000,
    refetchOnMount: true,
    refetchOnWindowFocus: false,
    retry: false,
    enabled,
    placeholderData: (previous) => previous,
  })
}

export function useSearch(q: string, page = 1) {
  return useQuery({
    queryKey: ['search', q, page],
    queryFn: () => api.get<PagedResults>(`/api/search?q=${encodeURIComponent(q)}&page=${page}`),
    enabled: q.trim().length > 0,
    staleTime: 10 * 60_000,
    retry: false,
    placeholderData: (prev) => prev,
  })
}

export type BrowseType = 'all' | 'movie' | 'tv'
export type BrowseSort = 'popular' | 'top' | 'new'

/** The personalized shelves on their own, for one kind of thing.
 *
 * Films and Series are separate pages, so each asks for its own shelves
 * rather than filtering the home page's: a "Picked for you" built only from
 * series is a different and better answer than the general one with the
 * films stripped out of it. */
export function useForYou(media: 'all' | 'movie' | 'tv') {
  return useQuery({
    queryKey: ['for-you', media],
    queryFn: () => api.get<{ rows: HomeRow[] }>(`/api/for-you?media=${media}`),
    staleTime: 10 * 60_000,
    refetchOnWindowFocus: false,
    retry: false,
    placeholderData: (previous) => previous,
  })
}

export function useBrowse(
  type: BrowseType,
  genre: string | null,
  sort: BrowseSort,
  page: number,
  language: string | null = null,
) {
  const genrePart = genre ? `&genre=${encodeURIComponent(genre)}` : ''
  const langPart = language ? `&language=${language}` : ''
  return useQuery({
    queryKey: ['browse', type, genre, sort, page, language],
    queryFn: () =>
      api.get<PagedResults>(
        `/api/browse?type=${type}${genrePart}${langPart}&sort=${sort}&page=${page}`,
      ),
    staleTime: 10 * 60_000,
    retry: false,
    placeholderData: (prev) => prev,
  })
}

export type CombinedGenre = { name: string; movie_ids: number[]; tv_ids: number[] }

export function useGenres() {
  return useQuery({
    queryKey: ['genres'],
    queryFn: () =>
      api.get<{
        movie: { id: number; name: string }[]
        tv: { id: number; name: string }[]
        combined: CombinedGenre[]
      }>('/api/genres'),
    staleTime: 24 * 60 * 60_000,
    retry: false,
  })
}

export function useTitle(type: string, tmdbId: string | number) {
  return useQuery({
    queryKey: ['title', type, String(tmdbId)],
    queryFn: () => api.get<TitleDetail>(`/api/titles/${type}/${tmdbId}`),
    staleTime: 10 * 60_000,
    retry: false,
  })
}
