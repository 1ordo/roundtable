import { motion } from 'motion/react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { img, type TitleCard } from '../api/catalog'
import { WatchedWholeFranchise } from './WatchedWholeFranchise'

type NextUpEntry = {
  title: TitleCard
  collection_name: string
  collection_id: number
  reason: string
  remaining: number
}

/* Finishing one part of a franchise is the clearest statement anyone makes
   about what they want next, so it gets answered directly. */
export function NextUp() {
  const { data } = useQuery({
    queryKey: ['next-up'],
    queryFn: () => api.get<NextUpEntry[]>('/api/next-up'),
    retry: false,
    staleTime: 5 * 60_000,
  })

  if (!data || data.length === 0) return null

  return (
    <section className="mb-10 min-w-0">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Next up</h2>
      <p className="mt-1 text-sm text-muted">Franchises you started and have not finished.</p>

      <div className="wd-scroller mt-4 flex gap-4 pb-3">
        {data.map((entry, i) => (
          <motion.div
            key={`${entry.title.type}-${entry.title.tmdb_id}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.05, 0.3), duration: 0.4 }}
            className="w-72 shrink-0"
          >
            {/* The card is a link, so the button lives beside it rather
                than inside it: a button nested in an anchor navigates as
                well as acting. */}
            <div className="wd-plate wd-plate--hover p-3">
              <Link
                to={`/app/title/${entry.title.type}/${entry.title.tmdb_id}`}
                className="group flex gap-3"
              >
                <img
                  src={img(entry.title.poster_path, 'w185') ?? ''}
                  alt={entry.title.name}
                  loading="lazy"
                  className="h-28 w-20 shrink-0 rounded-md object-cover"
                />
                <div className="min-w-0">
                  <p className="wd-eyebrow wd-eyebrow--ember">
                    {entry.reason}
                  </p>
                  <p className="mt-1 truncate font-display text-base">{entry.title.name}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">{entry.collection_name}</p>
                  <p className="mt-1.5 text-xs text-muted">
                    {entry.remaining === 1
                      ? 'The last one you have not seen'
                      : `${entry.remaining} left in the series`}
                  </p>
                </div>
              </Link>
              <div className="mt-3 border-t border-line pt-3">
                <WatchedWholeFranchise collectionId={entry.collection_id} compact />
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
