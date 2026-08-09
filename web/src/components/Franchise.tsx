import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { TitleCard } from '../api/catalog'
import { PosterCard } from './PosterCard'
import { WatchedWholeFranchise } from './WatchedWholeFranchise'

type CollectionOut = {
  id: number
  name: string
  overview: string | null
  parts: TitleCard[]
  watched_count: number
  in_list_count: number
  times_all_watched: number
}

/* The whole franchise, in release order, with one button to save the lot. */
export function Franchise({
  collectionId,
  currentTmdbId,
}: {
  collectionId: number
  currentTmdbId: number
}) {
  const queryClient = useQueryClient()
  const [result, setResult] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['collection', collectionId],
    queryFn: () => api.get<CollectionOut>(`/api/collections/${collectionId}`),
    retry: false,
  })

  const addAll = useMutation({
    mutationFn: (shared: boolean) =>
      api.post<{ added: number; already_there: number; list_name: string }>('/api/lists/bulk', {
        titles: (data?.parts ?? []).map((p) => ({ type: p.type, tmdb_id: p.tmdb_id })),
        shared,
      }),
    onSuccess: (res) => {
      setResult(
        res.added === 0
          ? `Everything was already on ${res.list_name}.`
          : `Added ${res.added} to ${res.list_name}${
              res.already_there ? `, ${res.already_there} were already there` : ''
            }.`,
      )
      queryClient.invalidateQueries({ queryKey: ['lists'] })
      queryClient.invalidateQueries({ queryKey: ['collection', collectionId] })
    },
  })

  if (!data || data.parts.length < 2) return null

  const remaining = data.parts.length - data.watched_count

  return (
    <section className="mt-12 min-w-0">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-2xl font-medium">{data.name}</h2>
          <p className="mt-1 text-sm text-muted">
            {data.parts.length} parts in release order
            {data.watched_count > 0 && `, you have seen ${data.watched_count}`}
            {data.watched_count > 0 && remaining > 0 && `, ${remaining} to go`}
            {data.times_all_watched > 0 &&
              `. You have been through all of it ${data.times_all_watched === 1 ? 'once' : `${data.times_all_watched} times`}.`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={() => addAll.mutate(false)}
            disabled={addAll.isPending}
            className="rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember disabled:opacity-50"
          >
            {addAll.isPending ? 'Saving' : 'Add the whole franchise'}
          </motion.button>
          <WatchedWholeFranchise collectionId={data.id} rounds={data.times_all_watched} compact />
        </div>
      </div>

      <AnimatePresence>
        {result && (
          <motion.p
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 overflow-hidden text-sm text-nitrate"
          >
            {result}
          </motion.p>
        )}
      </AnimatePresence>

      <div className="wd-scroller mt-4 flex gap-4 pb-3">
        {data.parts.map((part, i) => (
          <div
            key={`${part.type}-${part.tmdb_id}`}
            className={part.tmdb_id === currentTmdbId ? 'opacity-45' : undefined}
          >
            <PosterCard title={part} index={i} />
          </div>
        ))}
      </div>
    </section>
  )
}
