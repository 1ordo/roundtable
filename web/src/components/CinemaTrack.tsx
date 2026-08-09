import { motion } from 'motion/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'

type Entry = { card: { tmdb_id: number }; in_cinemas_now: boolean }

/* Whether this film is on the cinema list, read from the one small cinema
   query the page already needs rather than a per-title lookup. */
export function CinemaTrack({ tmdbId }: { tmdbId: number }) {
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ['cinema'],
    queryFn: () => api.get<{ tracking: Entry[]; now_showing: Entry[] }>('/api/cinema'),
    staleTime: 10 * 60_000,
  })
  const mine = (data?.tracking ?? []).find((t) => t.card.tmdb_id === tmdbId)
  const tracked = mine !== undefined
  // Showing now either because the tracked entry says so, or because it is
  // in the local now-playing list.
  const showing =
    mine?.in_cinemas_now || (data?.now_showing ?? []).some((t) => t.card.tmdb_id === tmdbId)

  const toggle = useMutation({
    mutationFn: () =>
      tracked
        ? api.delete(`/api/cinema/track?type=movie&tmdb_id=${tmdbId}`)
        : api.post('/api/cinema/track', { type: 'movie', tmdb_id: tmdbId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cinema'] }),
  })

  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      disabled={toggle.isPending}
      onClick={() => toggle.mutate()}
      aria-pressed={tracked}
      className={clsx(
        'mt-3 flex items-center gap-2 rounded-[4px] border px-4 py-2 text-sm transition-colors disabled:opacity-50',
        tracked
          ? 'border-ember bg-ember/10 text-ember'
          : 'border-line bg-panel text-muted hover:border-ember hover:text-ember',
      )}
    >
      <svg
        viewBox="0 0 24 24"
        className="h-4 w-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        aria-hidden
      >
        <path d="M4 9h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1ZM3 9l18-2.5" />
      </svg>
      {tracked
        ? showing
          ? 'On your cinema list'
          : 'Telling you when it opens'
        : showing
          ? 'In cinemas now, add it'
          : 'See it in a cinema'}
    </motion.button>
  )
}
