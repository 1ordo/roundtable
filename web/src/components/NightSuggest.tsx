import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { img } from '../api/catalog'
import { useQueueTitle, type Night } from '../api/social'

type Suggestion = {
  tmdb_id: number
  type: string
  name: string
  poster_path: string | null
  year: number | null
  tmdb_rating: number | null
  closest_to: string | null
  in_queue: boolean
}

type SuggestionsOut = {
  results: Suggestion[]
  considered: string[]
  without_taste: string[]
}

/* Suggestions for everyone who is actually coming, with a dial per person.
 *
 * The weight is a nudge and not a veto: the API clamps it to between 0.1 and
 * 3, because past that the blend stops being a compromise and becomes one
 * person's taste wearing everyone else's name. */
export function NightSuggest({ night }: { night: Night }) {
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [shown, setShown] = useState<Suggestion[]>([])
  const [seen, setSeen] = useState<number[]>([])
  const [info, setInfo] = useState<SuggestionsOut | null>(null)
  const queue = useQueueTitle()

  const coming = night.members.filter((m) => m.status === 'accepted')

  const suggest = useMutation({
    mutationFn: (more: boolean) =>
      api.post<SuggestionsOut>(`/api/nights/${night.id}/suggestions`, {
        weights,
        seen: more ? seen : [],
      }),
    onSuccess: (data, more) => {
      setInfo(data)
      setShown(more ? [...shown, ...data.results] : data.results)
      setSeen((current) => [...current, ...data.results.map((r) => r.tmdb_id)])
    },
  })

  function setWeight(username: string, value: number) {
    setWeights({ ...weights, [username]: value })
  }

  return (
    <div className="mt-5 rounded-md border border-line bg-panel-2/60 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="wd-eyebrow">Suggest for the room</p>
        {coming.length > 1 && (
          <p className="text-[11px] text-muted">
            Blended from {coming.length} people. Slide to say who leans hardest.
          </p>
        )}
      </div>

      {/* One slider per person who said yes. With a single person there is
          nothing to balance, so the row is not drawn at all. */}
      {coming.length > 1 && (
        <div className="mt-4 flex flex-col gap-3">
          {coming.map((member) => {
            const value = weights[member.username] ?? 1
            return (
              <label key={member.username} className="flex items-center gap-3">
                <span className="w-24 shrink-0 truncate text-sm">{member.username}</span>
                <input
                  type="range"
                  min={0.2}
                  max={3}
                  step={0.1}
                  value={value}
                  onChange={(e) => setWeight(member.username, Number(e.target.value))}
                  className="h-1 min-w-0 flex-1 cursor-pointer accent-ember"
                  aria-label={`How much ${member.username} counts`}
                />
                <span className="w-10 shrink-0 text-right font-mono text-[11px] text-muted">
                  {value.toFixed(1)}x
                </span>
              </label>
            )
          })}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <motion.button
          whileTap={{ scale: 0.97 }}
          disabled={suggest.isPending}
          onClick={() => suggest.mutate(false)}
          className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
        >
          {suggest.isPending && shown.length === 0 ? 'Thinking' : 'Suggest something'}
        </motion.button>
        {shown.length > 0 && (
          <button
            disabled={suggest.isPending}
            onClick={() => suggest.mutate(true)}
            className="rounded-[4px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:border-ember hover:text-ember disabled:opacity-50"
          >
            {suggest.isPending ? 'Finding more' : 'More like these'}
          </button>
        )}
      </div>

      {suggest.isError && (
        <p className="mt-3 text-xs text-danger">
          Could not work that out. The suggestion engine needs the AI features switched on.
        </p>
      )}

      {info && info.without_taste.length > 0 && (
        <p className="mt-3 text-xs text-muted">
          {info.without_taste.join(' and ')}{' '}
          {info.without_taste.length === 1 ? 'has' : 'have'} not watched enough yet to have a
          taste, so {info.without_taste.length === 1 ? 'they are' : 'they are'} only counted for
          what to leave out.
        </p>
      )}

      {shown.length > 0 && (
        <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
          <AnimatePresence initial={false}>
            {shown.map((pick, i) => (
              <motion.div
                key={`${pick.type}-${pick.tmdb_id}`}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.3 }}
                className="min-w-0"
              >
                <button
                  onClick={() =>
                    queue.mutate({ id: night.id, type: pick.type, tmdb_id: pick.tmdb_id })
                  }
                  disabled={pick.in_queue || queue.isPending}
                  className="group block w-full text-left"
                >
                  <span className="relative block">
                    {pick.poster_path ? (
                      <img
                        src={img(pick.poster_path, 'w185') ?? ''}
                        alt={pick.name}
                        loading="lazy"
                        className={clsx(
                          'aspect-[2/3] w-full rounded-lg object-cover ring-1 transition-all',
                          pick.in_queue
                            ? 'opacity-40 ring-line'
                            : 'ring-line group-hover:ring-ember',
                        )}
                      />
                    ) : (
                      <span className="flex aspect-[2/3] w-full items-center justify-center rounded-lg bg-panel p-1 text-center text-[10px] text-muted">
                        {pick.name}
                      </span>
                    )}
                    {!pick.in_queue && (
                      <span className="absolute inset-x-1 bottom-1 rounded bg-ember px-1 py-0.5 text-center font-mono text-[9px] font-bold text-ink opacity-0 transition-opacity group-hover:opacity-100">
                        ADD
                      </span>
                    )}
                    {pick.in_queue && (
                      <span className="absolute inset-x-1 bottom-1 rounded bg-panel px-1 py-0.5 text-center font-mono text-[9px] text-muted">
                        QUEUED
                      </span>
                    )}
                  </span>
                  <span className="mt-1.5 block truncate text-xs">{pick.name}</span>
                  {/* Only shown when one person is clearly nearer than the
                      rest, so it never labels a coin flip. */}
                  {pick.closest_to && (
                    <span className="block truncate font-mono text-[10px] text-muted">
                      most {pick.closest_to}
                    </span>
                  )}
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
