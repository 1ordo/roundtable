import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, LayoutGroup, motion, useInView, useReducedMotion } from 'motion/react'
import clsx from 'clsx'

/* The exploration setting, shown rather than described.
 *
 * The ratios are the real ones from the ranking code: EXPLORE_FRACTION is
 * 0.05 on comfort, 0.15 on balanced and 0.32 on bold. They are stated as
 * "about one in twenty / seven / three" and not rounded up, because the whole
 * point of the section is that the dial is honest.
 */
const MODES = [
  {
    key: 'comfort',
    label: 'Comfort',
    outside: 1,
    caption: 'About one pick in twenty comes from outside your cluster.',
  },
  {
    key: 'balanced',
    label: 'Balanced',
    outside: 2,
    caption: 'About one pick in seven comes from outside your cluster.',
  },
  {
    key: 'bold',
    label: 'Bold',
    outside: 4,
    caption: 'About one pick in three comes from outside your cluster.',
  },
] as const

type Mode = (typeof MODES)[number]['key']

function poster(path: string): string {
  return `/api/media/tmdb/w342/${path.replace(/^\//, '')}`
}

export function ExploreDemo({ posters }: { posters: string[] }) {
  const still = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const seen = useInView(ref, { once: true, amount: 0.4 })
  const [mode, setMode] = useState<Mode>('comfort')
  const [touched, setTouched] = useState(false)

  /* Move once, to show the control does something, then never again. A
     landing page that keeps animating while you read it is noise. */
  useEffect(() => {
    if (!seen || touched || still) return
    const timer = setTimeout(() => setMode('balanced'), 1200)
    return () => clearTimeout(timer)
  }, [seen, touched, still])

  const current = MODES.find((m) => m.key === mode) ?? MODES[1]
  const pool = posters.slice(0, 20)
  if (pool.length < 12) return null

  // The core twelve, with the last few swapped for lower ranked entries as
  // the dial goes up. Same set, reordered, so cards slide rather than blink.
  const core = pool.slice(0, 12 - current.outside)
  const outside = pool.slice(12, 12 + current.outside)
  const shown = [...core, ...outside]

  function pick(next: Mode) {
    setTouched(true)
    setMode(next)
  }

  return (
    <div ref={ref}>
      <LayoutGroup id="wd-explore">
        <div className="flex rounded-lg border border-line bg-panel/60 p-1">
          {MODES.map((option) => (
            <button
              key={option.key}
              onClick={() => pick(option.key)}
              aria-pressed={mode === option.key}
              className={clsx(
                'relative flex-1 rounded-[4px] px-4 py-2 text-sm transition-colors sm:flex-none sm:px-7',
                mode === option.key ? 'text-ink' : 'text-muted hover:text-fg',
              )}
            >
              {mode === option.key && (
                <motion.span
                  layoutId="wd-explore-pill"
                  className="absolute inset-0 rounded-[4px] bg-ember"
                  transition={{ type: 'spring', stiffness: 400, damping: 34 }}
                />
              )}
              <span className="relative">{option.label}</span>
            </button>
          ))}
        </div>

        <div className="mt-4 h-5">
          <AnimatePresence mode="wait">
            <motion.p
              key={current.key}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.22 }}
              className="text-sm text-muted"
            >
              {current.caption}
            </motion.p>
          </AnimatePresence>
        </div>

        <div className="mt-6 grid grid-cols-4 gap-3 sm:grid-cols-6 lg:grid-cols-12">
          <AnimatePresence mode="popLayout" initial={false}>
            {shown.map((path, index) => {
              const isOutside = index >= core.length
              return (
                <motion.div
                  key={path}
                  layout
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{
                    layout: { type: 'spring', stiffness: 320, damping: 32 },
                    duration: 0.25,
                  }}
                  className="relative min-w-0"
                >
                  <img
                    src={poster(path)}
                    alt=""
                    loading="lazy"
                    className={clsx(
                      'aspect-[2/3] w-full rounded-md object-cover ring-1 transition-all',
                      isOutside ? 'ring-ember/70' : 'ring-line',
                    )}
                  />
                  {isOutside && (
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="absolute inset-x-1 bottom-1 rounded-[4px] bg-ember px-1 py-0.5 text-center font-mono text-[8px] leading-tight font-bold text-ink"
                    >
                      OUTSIDE
                    </motion.span>
                  )}
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>
      </LayoutGroup>

      <p className="mt-4 font-mono text-[11px] text-muted">
        An illustration of the setting, using titles from this catalogue.
      </p>
    </div>
  )
}
