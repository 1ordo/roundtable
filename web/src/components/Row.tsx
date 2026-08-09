import { useCallback, useEffect, useState, type MouseEvent } from 'react'
import { motion } from 'motion/react'
import { api } from '../api/client'
import type { TitleCard } from '../api/catalog'
import clsx from 'clsx'
import { PosterCard } from './PosterCard'
import { motionOff } from '../lib/motion'

/* Native `behavior: 'smooth'` is unreliable (some engines silently ignore it),
   so the glide is driven here. Respects reduced motion by jumping instead. */
export function animateScroll(el: HTMLElement, to: number, onDone?: () => void) {
  const from = el.scrollLeft
  const distance = to - from
  if (Math.abs(distance) < 1) return
  // Jump when animation frames will not arrive: reduced motion, or a page
  // that is not being painted (background tab). Otherwise the row would
  // simply never move.
  if (motionOff() || document.hidden) {
    el.scrollLeft = to
    onDone?.()
    return
  }
  const duration = Math.min(600, 220 + Math.abs(distance) * 0.35)
  const start = performance.now()
  function step(now: number) {
    const progress = Math.min(1, (now - start) / duration)
    // easeOutCubic: quick departure, soft landing.
    const eased = 1 - Math.pow(1 - progress, 3)
    el.scrollLeft = from + distance * eased
    if (progress < 1) {
      requestAnimationFrame(step)
    } else {
      onDone?.()
    }
  }
  requestAnimationFrame(step)
}

/** Keeps asking a shelf for more, and remembers what it already has.
 *
 * The server rebuilds each page from the taste vector rather than holding a
 * cursor, so the seam between two pages can repeat a title when the vector
 * moved between requests. Deduping on arrival is cheaper and more robust
 * than making the server promise it never happens. */
function useMore(shelf: string | undefined, media: 'all' | 'movie' | 'tv', have: TitleCard[]) {
  const [extra, setExtra] = useState<TitleCard[]>([])
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  // A different shelf, or the same shelf rebuilt, starts over.
  useEffect(() => {
    setExtra([])
    setPage(0)
    setDone(false)
  }, [shelf, media])

  const load = useCallback(async () => {
    if (!shelf || loading || done) return
    setLoading(true)
    try {
      const next = page + 1
      const row = await api.get<{ items: TitleCard[] } | null>(
        `/api/for-you/more?shelf=${encodeURIComponent(shelf)}&media=${media}&page=${next}`,
      )
      const incoming = row?.items ?? []
      if (incoming.length === 0) {
        setDone(true)
        return
      }
      setExtra((current) => {
        const seen = new Set(
          [...have, ...current].map((item) => `${item.type}-${item.tmdb_id}`),
        )
        const fresh = incoming.filter((item) => !seen.has(`${item.type}-${item.tmdb_id}`))
        if (fresh.length === 0) setDone(true)
        return [...current, ...fresh]
      })
      setPage(next)
    } catch {
      // A shelf that will not extend is not worth an error state. The
      // titles already on screen are still the answer.
      setDone(true)
    } finally {
      setLoading(false)
    }
  }, [shelf, media, page, loading, done, have])

  return { extra, load, loading, done }
}

export function Row({
  title,
  items,
  shelf,
  media = 'all',
}: {
  title: string
  items: TitleCard[]
  /** Shelf key, when this row can be asked for more of itself. */
  shelf?: string
  media?: 'all' | 'movie' | 'tv'
}) {
  /* A shelf is a scroller until you ask for the whole thing, at which point
     it becomes a grid. Scrolling sideways for forty titles is worse than
     seeing them all at once, and the arrows stop being useful long before
     the row runs out. */
  const [expanded, setExpanded] = useState(false)
  const { extra, load, loading, done } = useMore(shelf, media, items)
  const shown = extra.length ? [...items, ...extra] : items
  const canLoadMore = Boolean(shelf) && !done
  // A callback ref in state, so the arrows re-render once the node exists
  // and always act on the node that is actually on screen.
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null)
  const [atStart, setAtStart] = useState(true)
  const [atEnd, setAtEnd] = useState(false)

  const refresh = useCallback(() => {
    if (!scroller) return
    setAtStart(scroller.scrollLeft <= 2)
    setAtEnd(scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 2)
  }, [scroller])

  useEffect(() => {
    refresh()
    if (!scroller) return
    const observer = new ResizeObserver(refresh)
    observer.observe(scroller)
    return () => observer.disconnect()
  }, [scroller, refresh, shown.length])

  function nudge(event: MouseEvent<HTMLButtonElement>, direction: 1 | -1) {
    // Resolve the strip from the button that was pressed. The arrows belong
    // to exactly one row, so this is always the right element and does not
    // depend on when the ref happened to attach.
    const el =
      event.currentTarget.closest('section')?.querySelector<HTMLDivElement>('.wd-scroller') ??
      scroller
    if (!el) return
    // Move by whole cards so nothing is left half cut off.
    const card = el.firstElementChild as HTMLElement | null
    const cardStep = card && card.offsetWidth ? card.offsetWidth + 16 : 176
    const perView = Math.max(1, Math.floor(el.clientWidth / cardStep) - 1)
    const target = el.scrollLeft + direction * cardStep * perView
    const clamped = Math.max(0, Math.min(target, el.scrollWidth - el.clientWidth))
    animateScroll(el, clamped, refresh)
  }

  if (shown.length === 0) return null

  return (
    <section className="group/row min-w-0">
      <div className="mb-3 flex items-center justify-between gap-4">
        <h2 className="font-display text-2xl font-semibold tracking-[0.02em] uppercase">{title}</h2>
        <div className="flex items-center gap-3">
        {shown.length > 6 && (
          <button
            onClick={() => setExpanded((open) => !open)}
            className="shrink-0 font-mono text-[11px] text-muted transition-colors hover:text-ember"
          >
            {expanded ? 'show less' : `see all ${shown.length}`}
          </button>
        )}
        <div className={clsx('hidden gap-1.5 md:flex', expanded && 'md:hidden')}>
          <motion.button
            whileTap={{ scale: 0.9 }}
            onClick={(e) => nudge(e, -1)}
            disabled={atStart}
            aria-label={`Scroll ${title} back`}
            className="rounded-full border border-line bg-panel p-1.5 text-muted transition-all hover:border-ember hover:text-ember disabled:pointer-events-none disabled:opacity-25"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 5l-7 7 7 7" />
            </svg>
          </motion.button>
          <motion.button
            whileTap={{ scale: 0.9 }}
            onClick={(e) => nudge(e, 1)}
            disabled={atEnd}
            aria-label={`Scroll ${title} forward`}
            className="rounded-full border border-line bg-panel p-1.5 text-muted transition-all hover:border-ember hover:text-ember disabled:pointer-events-none disabled:opacity-25"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 5l7 7-7 7" />
            </svg>
          </motion.button>
        </div>
        </div>
      </div>

      {expanded ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
        >
          {shown.map((item, i) => (
            <div key={`${item.type}-${item.tmdb_id}`} className="[&>div]:w-full">
              <PosterCard title={item} index={i % 12} />
            </div>
          ))}
          {canLoadMore && (
            <button
              onClick={load}
              disabled={loading}
              className="flex aspect-[2/3] w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line bg-panel/40 text-muted transition-colors hover:border-ember hover:text-ember disabled:opacity-50"
            >
              <span className="font-mono text-[11px]">{loading ? 'loading' : 'load more'}</span>
            </button>
          )}
        </motion.div>
      ) : (
      <div className="relative min-w-0">
        <div
          ref={setScroller}
          onScroll={refresh}
          className="wd-scroller flex gap-4 pb-3"
          tabIndex={0}
          role="group"
          aria-label={title}
        >
          {shown.map((item, i) => (
            <PosterCard key={`${item.type}-${item.tmdb_id}`} title={item} index={i} />
          ))}
          {canLoadMore && (
            /* A tile at the end of the strip rather than a button beneath
               it: scrolling to the end of a shelf is exactly the moment
               someone wants more of it, and that is where their eye already
               is. */
            <button
              onClick={load}
              disabled={loading}
              className="flex aspect-[2/3] w-36 shrink-0 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line bg-panel/40 text-muted transition-colors hover:border-ember hover:text-ember disabled:opacity-50 sm:w-40"
            >
              <span className="font-mono text-[11px]">{loading ? 'loading' : 'more'}</span>
              {!loading && (
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 5l7 7-7 7" />
                </svg>
              )}
            </button>
          )}
        </div>

        {/* Edge fades hint that there is more in that direction. */}
        {!atStart && (
          <div className="pointer-events-none absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-ink to-transparent" />
        )}
        {!atEnd && (
          <div className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-ink to-transparent" />
        )}
      </div>
      )}
    </section>
  )
}
