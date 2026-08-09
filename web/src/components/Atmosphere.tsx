import { motion, useReducedMotion, useScroll, useSpring, useTransform } from 'motion/react'

/* The page's light, as one fixed sheet.
 *
 * The old version lived inside the hero section, which is what made the page
 * look like it was overflowing out of a container: a radial vignette centred
 * below the hero was still at three quarters of full strength where the
 * section's overflow-hidden cut it off, so a full-width step appeared at that
 * line, brightest in the middle exactly like the edge of a rounded box.
 *
 * Fixed to the viewport there is no bottom edge in page space, so no seam can
 * form at any scroll position or zoom level. The rule that keeps it that way:
 * every gradient stop must reach transparent inside its own box, and no
 * ancestor of this element may set transform, filter, perspective,
 * backdrop-filter or contain, because any of those would make it resolve
 * against that ancestor instead of the viewport and bring the seam back.
 */
export function Atmosphere() {
  const still = useReducedMotion()
  const { scrollY } = useScroll()
  // The bloom leaves with the hero rather than sitting under the whole page.
  const raw = useTransform(scrollY, [0, 900], [0, -260])
  const bloomY = useSpring(raw, { stiffness: 120, damping: 30, mass: 0.6 })

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-ink">
      {/* Warm from the upper left, cool from the upper right. Both resolve to
          transparent well inside the viewport. */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `
            radial-gradient(120% 90% at 12% -12%,
              color-mix(in oklab, var(--color-ember) 15%, transparent) 0%,
              color-mix(in oklab, var(--color-ember) 5%, transparent) 26%,
              transparent 60%),
            radial-gradient(110% 85% at 88% -8%,
              color-mix(in oklab, var(--color-nitrate) 13%, transparent) 0%,
              color-mix(in oklab, var(--color-nitrate) 4%, transparent) 28%,
              transparent 62%)`,
        }}
      />
      <motion.div
        style={still ? undefined : { y: bloomY }}
        className="absolute top-[-10%] left-1/2 h-[70vh] w-[120vw] -translate-x-1/2"
      >
        <div
          className="h-full w-full"
          style={{
            backgroundImage:
              'radial-gradient(55% 50% at 50% 40%, color-mix(in oklab, var(--color-ember) 9%, transparent), transparent 70%)',
          }}
        />
      </motion.div>
      {/* A little grain so the large flat areas do not band on cheap panels. */}
      <div
        className="absolute inset-0 opacity-[0.035] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
    </div>
  )
}

/* A break that has no edge to lock onto: it reaches zero alpha at both ends,
   so it reads as a pause rather than as the side of a box. */
export function Hairline({ className = '' }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`h-px w-full bg-[linear-gradient(to_right,transparent,var(--color-line),transparent)] ${className}`}
    />
  )
}
