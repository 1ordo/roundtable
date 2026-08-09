import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { motionOff } from '../lib/motion'

const NUMBER_MS = 420
const BOOT_KEY = 'wd-booted'

/* The academy leader: the countdown a projectionist runs before the
   picture starts. Three sweeps of the hand, a changeover flash, and the
   app is on screen. Plays once per session; a reload mid-evening goes
   straight to the picture. Under reduced motion it never mounts at all,
   because the honest version of this animation is no animation. */
export function useBootSequence(): boolean {
  const [booting] = useState(
    () => !sessionStorage.getItem(BOOT_KEY) && !motionOff(),
  )
  useEffect(() => {
    if (booting) sessionStorage.setItem(BOOT_KEY, '1')
  }, [booting])
  return booting
}

export function LeaderBoot({ onDone }: { onDone: () => void }) {
  // 3 → 2 → 1 → wordmark → gone.
  const [count, setCount] = useState(3)

  /* The whole sequence is scheduled once, on mount. Deriving each step
     from the previous render made the timer restart whenever the parent
     re-rendered (a resolving query was enough), which could hold the
     countdown at 3 forever. onDone lives in a ref for the same reason. */
  const doneRef = useRef(onDone)
  doneRef.current = onDone
  useEffect(() => {
    const timers = [
      window.setTimeout(() => setCount(2), NUMBER_MS),
      window.setTimeout(() => setCount(1), NUMBER_MS * 2),
      window.setTimeout(() => setCount(0), NUMBER_MS * 3),
      window.setTimeout(() => doneRef.current(), NUMBER_MS * 3 + 360),
    ]
    return () => timers.forEach((t) => window.clearTimeout(t))
  }, [])

  return (
    <motion.div
      aria-hidden
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.28, ease: 'easeOut' } }}
      className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden bg-ink"
    >
      {/* Frame crosshair, corner to corner. */}
      <div className="absolute inset-x-0 top-1/2 h-px bg-fg/10" />
      <div className="absolute inset-y-0 left-1/2 w-px bg-fg/10" />

      {/* Corner frame ticks. */}
      {(['top-5 left-5 border-t border-l', 'top-5 right-5 border-t border-r', 'bottom-5 left-5 border-b border-l', 'bottom-5 right-5 border-b border-r'] as const).map(
        (pos) => (
          <div key={pos} className={`absolute h-5 w-5 border-fg/25 ${pos}`} />
        ),
      )}

      <div className="relative flex h-[19rem] w-[19rem] items-center justify-center">
        <svg viewBox="0 0 304 304" className="absolute inset-0 h-full w-full">
          <circle cx="152" cy="152" r="146" fill="none" stroke="var(--color-line)" strokeWidth="1.5" />
          <circle cx="152" cy="152" r="104" fill="none" stroke="var(--color-line)" strokeWidth="1" />
        </svg>

        {count > 0 && (
          <>
            {/* One full rotation of the hand per number. Keyed so the CSS
                animation restarts each count. */}
            <svg
              key={`hand-${count}`}
              viewBox="0 0 304 304"
              className="absolute inset-0 h-full w-full"
              style={{ animation: `wd-sweep ${NUMBER_MS}ms linear` }}
            >
              <path
                d="M152 152V10"
                stroke="var(--color-ember)"
                strokeWidth="2.5"
                strokeLinecap="round"
              />
            </svg>

            <AnimatePresence mode="popLayout">
              <motion.span
                key={count}
                initial={{ opacity: 0, scale: 1.14 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.13 }}
                className="font-display text-[11rem] leading-none font-semibold text-fg"
              >
                {count}
              </motion.span>
            </AnimatePresence>
          </>
        )}

        {/* The wordmark holds one beat, then the room lights come up. No
            flash frame: a bright full-screen blink is a strobe, not a
            flourish. */}
        {count === 0 && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.18 }}
            className="font-display text-4xl font-semibold tracking-[0.14em] text-fg uppercase"
          >
            Watchpile
          </motion.p>
        )}
      </div>

      <p className="absolute bottom-10 font-mono text-[10px] tracking-[0.3em] text-muted uppercase">
        {count > 0 ? 'Picture start' : 'Now showing'}
      </p>
    </motion.div>
  )
}
