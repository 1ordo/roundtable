import { motion, useReducedMotion, useScroll, useSpring, useTransform } from 'motion/react'
import { useRef } from 'react'

const SETTLE = [0.16, 1, 0.3, 1] as const

/* The only rectangle left on the page, and it is a product surface rather
   than a container: a hairline ring, a shadow that bleeds out into the
   atmosphere instead of landing on a band, and a bloom behind it.
 *
 * The tilt uses transformPerspective on the animated element itself. A
 * wrapper with a perspective property would become a containing block and
 * take the fixed atmosphere layer down with it, which is the seam coming
 * back by another route.
 */
export function DeviceFrame({
  src,
  alt,
  label,
  priority = false,
  tilt = false,
  parallax = 0,
  className = '',
}: {
  src: string
  alt: string
  label: string
  priority?: boolean
  tilt?: boolean
  parallax?: number
  className?: string
}) {
  const still = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],
  })
  const raw = useTransform(scrollYProgress, [0, 1], [parallax, -parallax])
  const y = useSpring(raw, { stiffness: 120, damping: 30, mass: 0.6 })

  return (
    <motion.div
      ref={ref}
      style={still || !parallax ? undefined : { y }}
      className={`relative ${className}`}
    >
      {/* Bloom, well outside the frame so its own falloff finishes in open air. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-x-12 -inset-y-10 -z-10 blur-3xl"
        style={{
          backgroundImage:
            'radial-gradient(50% 50% at 50% 50%, color-mix(in oklab, var(--color-ember) 14%, transparent), transparent 72%)',
        }}
      />
      <motion.figure
        /* No opacity here either: a screenshot that never fades in is a
           screenshot nobody sees. Only the settle is animated. */
        initial={
          still ? false : tilt ? { y: 56, rotateX: 14, scale: 0.94 } : { y: 22 }
        }
        whileInView={{ y: 0, rotateX: 0, scale: 1 }}
        viewport={{ once: true, amount: 0.25 }}
        transition={{ duration: tilt ? 1.0 : 0.5, ease: SETTLE }}
        style={{ transformPerspective: 1400 }}
        className="overflow-hidden rounded-lg ring-1 ring-line shadow-[0_50px_140px_-30px_rgba(0,0,0,0.85)]"
      >
        {/* A real label, not a fake browser bar. It is an app, not a website. */}
        <figcaption className="flex items-center gap-2 border-b border-line bg-panel/90 px-4 py-2.5">
          <span aria-hidden className="flex gap-1.5">
            <span className="h-2 w-2 rounded-full bg-panel-2" />
            <span className="h-2 w-2 rounded-full bg-panel-2" />
            <span className="h-2 w-2 rounded-full bg-panel-2" />
          </span>
          <span className="font-mono text-[11px] text-muted">{label}</span>
        </figcaption>
        <picture>
          <source srcSet={src.replace(/\.png$/, '.webp')} type="image/webp" />
          <img
            src={src}
            alt={alt}
            width={1440}
            height={900}
            loading={priority ? 'eager' : 'lazy'}
            decoding={priority ? 'sync' : 'async'}
            className="block w-full"
          />
        </picture>
      </motion.figure>
    </motion.div>
  )
}
