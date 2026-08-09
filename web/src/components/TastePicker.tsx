import { useState } from 'react'
import { motion } from 'motion/react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { img } from '../api/catalog'

type Poster = { tmdb_id: number; type: string; name: string; poster_path: string | null }

const WANTED = 5

/* Pick a few things you like, so the first shelves mean something.
 *
 * The alternative is a cold start where every suggestion is just whatever
 * is popular, which is exactly the corridor the whole app is meant to avoid.
 * Five is the floor rather than a target: past about a dozen the vector
 * stops moving much and it starts feeling like a chore. */
export function TastePicker({
  chosen,
  onChange,
}: {
  chosen: { type: string; tmdb_id: number }[]
  onChange: (next: { type: string; tmdb_id: number }[]) => void
}) {
  const [page, setPage] = useState(0)
  const { data, isLoading } = useQuery({
    queryKey: ['taste-seed'],
    queryFn: () => api.get<{ posters: Poster[] }>('/api/onboarding/popular'),
    staleTime: Infinity,
  })

  const all = data?.posters ?? []
  const size = 12
  const pages = Math.max(1, Math.ceil(all.length / size))
  const shown = all.slice(page * size, page * size + size)
  const picked = new Set(chosen.map((c) => `${c.type}-${c.tmdb_id}`))

  function toggle(poster: Poster) {
    const key = `${poster.type}-${poster.tmdb_id}`
    onChange(
      picked.has(key)
        ? chosen.filter((c) => `${c.type}-${c.tmdb_id}` !== key)
        : [...chosen, { type: poster.type, tmdb_id: poster.tmdb_id }],
    )
  }

  return (
    <div>
      <div className="grid grid-cols-4 gap-2.5 sm:grid-cols-6">
        {isLoading &&
          [...Array(12)].map((_, i) => (
            <div key={i} className="aspect-[2/3] animate-pulse rounded-[6px] bg-panel-2" />
          ))}
        {shown.map((poster) => {
          const on = picked.has(`${poster.type}-${poster.tmdb_id}`)
          return (
            <motion.button
              key={`${poster.type}-${poster.tmdb_id}`}
              whileTap={{ scale: 0.95 }}
              onClick={() => toggle(poster)}
              aria-pressed={on}
              title={poster.name}
              className="relative min-w-0"
            >
              {poster.poster_path ? (
                <img
                  src={img(poster.poster_path, 'w185') ?? ''}
                  alt={poster.name}
                  loading="lazy"
                  className={clsx(
                    'aspect-[2/3] w-full rounded-[6px] object-cover ring-2 transition-all',
                    on ? 'ring-ember' : 'opacity-70 ring-transparent hover:opacity-100',
                  )}
                />
              ) : (
                <span className="flex aspect-[2/3] w-full items-center justify-center rounded-[6px] bg-panel-2 p-1 text-center text-[9px] text-muted">
                  {poster.name}
                </span>
              )}
              {on && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-ember text-ink"
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-3 w-3"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.5"
                    aria-hidden
                  >
                    <path d="M5 12l5 5L19 7" />
                  </svg>
                </motion.span>
              )}
            </motion.button>
          )
        })}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <p className="text-xs text-muted">
          {chosen.length < WANTED
            ? `Pick ${WANTED - chosen.length} more`
            : `${chosen.length} picked. Add more or carry on.`}
        </p>
        {pages > 1 && (
          <button
            onClick={() => setPage((p) => (p + 1) % pages)}
            className="rounded-[4px] border border-line px-3 py-1 text-xs text-muted transition-colors hover:border-ember hover:text-ember"
          >
            Show me others
          </button>
        )}
      </div>
    </div>
  )
}

export { WANTED as TASTE_MINIMUM }
