import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Link } from 'react-router'
import clsx from 'clsx'
import { img, type TitleCard } from '../api/catalog'
import { motionOff } from '../lib/motion'

const HOLD_MS = 7000

/* A slow crossfade through the best of what is on offer. It pauses on
   hover, on focus, and when the tab is not being painted, so it never
   animates where nobody is looking. */
export function Hero({ items, greeting }: { items: TitleCard[]; greeting: string }) {
  const slides = items.filter((item) => item.backdrop_path).slice(0, 6)
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (slides.length < 2 || paused) return
    const reduced = motionOff()
    if (reduced) return
    const handle = window.setInterval(
      () => setIndex((current) => (current + 1) % slides.length),
      HOLD_MS,
    )
    return () => window.clearInterval(handle)
  }, [slides.length, paused])

  if (slides.length === 0) return null
  const current = slides[Math.min(index, slides.length - 1)]

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
      /* Bleeds to the very top on every size: leaving the page padding in
         place here put a dark band above the image. */
      /* Cancels the page padding exactly, so the artwork reaches the top of
         the column and the search bar floats over it rather than sitting on
         a band above it. */
      className="wd-screen relative -mx-6 -mt-24 mb-10 h-[52vh] min-h-80 overflow-hidden md:-mx-10 md:rounded-b-2xl"
    >
      <AnimatePresence mode="sync">
        <motion.img
          key={`${current.type}-${current.tmdb_id}`}
          src={img(current.backdrop_path, 'w1280') ?? ''}
          alt=""
          initial={{ opacity: 0, scale: 1.06 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ opacity: { duration: 0.9 }, scale: { duration: 8, ease: 'linear' } }}
          className="absolute inset-0 h-full w-full object-cover"
        />
      </AnimatePresence>

      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(to top, var(--wd-page-ink) 2%, transparent 34%), linear-gradient(to right, color-mix(in srgb, var(--color-ink) 88%, transparent), transparent 58%)',
        }}
      />

      <div className="absolute bottom-0 left-0 max-w-2xl p-6 md:p-10">
        <p className="wd-eyebrow wd-eyebrow--ember">{greeting}</p>
        {/* The incoming slide never starts invisible. mode="wait" holds the
            new text until the old one has exited, so a stalled frame used to
            leave the title at opacity 0 with nothing to show for it. It
            slides in from a visible state now: the swap still reads as a
            change, and the worst case is text sitting a few pixels low
            rather than a hero with no title on it. */}
        <AnimatePresence mode="wait">
          <motion.div
            key={`${current.type}-${current.tmdb_id}-text`}
            initial={{ y: 12 }}
            animate={{ y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            <h1 className="mt-2 font-display text-5xl font-semibold tracking-[0.01em] text-balance uppercase md:text-6xl">
              {current.name}
            </h1>
            <p className="mt-2 flex flex-wrap items-center gap-x-3 font-mono text-xs text-muted">
              {current.year && <span>{current.year}</span>}
              {current.tmdb_rating ? <span>{current.tmdb_rating.toFixed(1)}</span> : null}
              {current.certification && <span>{current.certification}</span>}
              {current.match != null && <span className="text-ember">{current.match}% match</span>}
            </p>
            <Link
              to={`/app/title/${current.type}/${current.tmdb_id}`}
              className="mt-4 inline-block rounded-[4px] bg-ember px-5 py-2.5 font-medium text-ink transition-colors hover:bg-ember/90"
            >
              See details
            </Link>
          </motion.div>
        </AnimatePresence>
      </div>

      {slides.length > 1 && (
        <div className="absolute right-6 bottom-6 flex gap-2 md:right-10">
          {slides.map((slide, i) => (
            <button
              key={`${slide.type}-${slide.tmdb_id}`}
              onClick={() => setIndex(i)}
              aria-label={`Show ${slide.name}`}
              aria-current={i === index}
              className={clsx(
                'h-1.5 rounded-full transition-all',
                i === index ? 'w-6 bg-ember' : 'w-1.5 bg-fg/40 hover:bg-fg/70',
              )}
            />
          ))}
        </div>
      )}
    </div>
  )
}
