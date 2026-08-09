import { useEffect, useRef } from 'react'
import { animate, useInView, useReducedMotion } from 'motion/react'

/* A figure that counts up once when it comes into view.
 *
 * Under reduced motion it renders the final value immediately rather than a
 * frozen zero, which is the usual bug in this pattern: the animation is what
 * was skipped, not the number. */
export function Counter({ to, label }: { to: number; label: string }) {
  const still = useReducedMotion()
  const ref = useRef<HTMLParagraphElement>(null)
  const seen = useInView(ref, { once: true, amount: 0.6 })

  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (still || !seen) {
      if (still) node.textContent = to.toLocaleString()
      return
    }
    const controls = animate(0, to, {
      duration: 1.2,
      ease: 'easeOut',
      onUpdate: (value) => {
        node.textContent = Math.round(value).toLocaleString()
      },
    })
    return () => controls.stop()
  }, [seen, to, still])

  return (
    <div>
      <p
        ref={ref}
        className="font-display text-4xl font-semibold tracking-[0.01em] tabular-nums text-ember md:text-5xl"
        aria-label={`${to.toLocaleString()} ${label}`}
      >
        {still ? to.toLocaleString() : '0'}
      </p>
      <p className="mt-1 font-mono text-[10px] tracking-[0.2em] text-muted uppercase">{label}</p>
    </div>
  )
}
