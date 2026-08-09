import { motion } from 'motion/react'
import { Link } from 'react-router'
import { img } from '../api/catalog'
import {
  useDeleteEvent,
  useHistory,
  useUpdateEvent,
  type WatchEventOut,
} from '../api/tracking'

function RatingDots({
  value,
  onChange,
}: {
  value: number | null
  onChange: (rating: number) => void
}) {
  return (
    <div className="flex items-center gap-1" role="radiogroup" aria-label="Rating out of ten">
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
        <button
          key={n}
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} out of 10`}
          onClick={() => onChange(n)}
          className="group p-0.5"
        >
          <span
            className={
              value != null && n <= value
                ? 'block h-2 w-2 rounded-full bg-ember transition-transform group-hover:scale-150'
                : 'block h-2 w-2 rounded-full bg-line transition-transform group-hover:scale-150 group-hover:bg-ember/50'
            }
          />
        </button>
      ))}
      {value != null && <span className="ml-1.5 font-mono text-xs text-muted">{value}/10</span>}
    </div>
  )
}

function EventRow({ event, index }: { event: WatchEventOut; index: number }) {
  const updateEvent = useUpdateEvent()
  const deleteEvent = useDeleteEvent()
  const poster = img(event.title.poster_path, 'w185')
  const date = new Date(event.watched_at)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.4), duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="wd-plate flex items-center gap-4 p-3"
    >
      <Link to={`/app/title/${event.title.type}/${event.title.tmdb_id}`} className="shrink-0">
        {poster ? (
          <img src={poster} alt={event.title.name} className="h-20 w-14 rounded-md object-cover" />
        ) : (
          <div className="flex h-20 w-14 items-center justify-center rounded-md bg-panel-2 text-xs text-muted">
            {event.title.name.slice(0, 8)}
          </div>
        )}
      </Link>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <Link
            to={`/app/title/${event.title.type}/${event.title.tmdb_id}`}
            className="truncate font-display text-lg font-medium hover:text-ember"
          >
            {event.title.name}
          </Link>
          {event.title.year && (
            <span className="font-mono text-xs text-muted">{event.title.year}</span>
          )}
          {event.source === 'import' && (
            <span className="rounded border border-line px-1.5 font-mono text-[10px] text-muted uppercase">
              import
            </span>
          )}
        </div>
        <p className="mt-0.5 font-mono text-xs text-muted">
          {date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
        </p>
        <div className="mt-2">
          <RatingDots
            value={event.rating_10}
            onChange={(rating) => updateEvent.mutate({ id: event.id, rating_10: rating })}
          />
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <motion.button
          whileTap={{ scale: 1.35 }}
          onClick={() => updateEvent.mutate({ id: event.id, loved: !event.loved })}
          aria-label={event.loved ? 'Remove loved mark' : 'Mark as loved'}
          aria-pressed={event.loved}
          className="p-2"
        >
          <svg
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill={event.loved ? 'var(--color-ember)' : 'none'}
            stroke={event.loved ? 'var(--color-ember)' : 'currentColor'}
            strokeWidth="1.6"
            className={event.loved ? '' : 'text-muted'}
          >
            <path d="M12 20.5C7 16.5 3.5 13.3 3.5 9.6 3.5 7 5.6 5 8 5c1.6 0 3.1.8 4 2.2C12.9 5.8 14.4 5 16 5c2.4 0 4.5 2 4.5 4.6 0 3.7-3.5 6.9-8.5 10.9Z" />
          </svg>
        </motion.button>
        <button
          onClick={() => deleteEvent.mutate(event.id)}
          aria-label="Remove from history"
          className="p-2 text-muted transition-colors hover:text-danger"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-9 0 1 13h8l1-13" />
          </svg>
        </button>
      </div>
    </motion.div>
  )
}

export function History() {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useHistory()
  const events = data?.pages.flatMap((page) => page.events) ?? []
  const total = data?.pages[0]?.total ?? 0

  return (
    <div>
      <header className="mb-8">
        <p className="wd-eyebrow">Your shelf</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          History
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          {data ? `${total} watched` : 'Everything you have watched, rated, and loved.'}
        </p>
      </header>

      {data && events.length === 0 && (
        <p className="max-w-md text-muted">
          Nothing watched yet. Mark a title as watched from its page, or import your Netflix
          history from Settings.
        </p>
      )}

      <div className="flex max-w-3xl flex-col gap-3">
        {events.map((event, i) => (
          <EventRow key={event.id} event={event} index={i} />
        ))}
      </div>

      {hasNextPage && (
        <div className="mt-8 max-w-3xl text-center">
          <button
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="rounded-[4px] border border-line bg-panel px-6 py-2.5 text-sm transition-colors hover:border-ember hover:text-ember disabled:opacity-50"
          >
            {isFetchingNextPage ? 'Loading' : `Load more (${events.length} of ${total})`}
          </button>
        </div>
      )}
    </div>
  )
}
