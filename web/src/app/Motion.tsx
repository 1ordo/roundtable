import { useEffect, useState } from 'react'
import { MotionConfig } from 'motion/react'

/* One switch for every animation in the app.
 *
 * MotionConfig's reducedMotion="user" reads the operating system setting and
 * nothing else, but this app also has its own toggle in Settings, written to
 * a data attribute on the document element. Honouring only one of the two
 * means the in-app switch does nothing to any motion/react component, which
 * is most of them.
 *
 * "always" rather than "never" for the reduced case: motion/react keeps
 * opacity and colour transitions and drops transform and layout ones, which
 * is the right reading of the preference. Nothing that has to be legible is
 * ever gated on an animation, so losing the movement loses nothing.
 */
export function Motion({ children }: { children: React.ReactNode }) {
  const [reduced, setReduced] = useState(
    () => document.documentElement.dataset.reduceMotion === 'true'
  )

  useEffect(() => {
    // The attribute is set from the user's saved preference after the
    // profile loads, so this has to react to it rather than read it once.
    const target = document.documentElement
    const observer = new MutationObserver(() => {
      setReduced(target.dataset.reduceMotion === 'true')
    })
    observer.observe(target, { attributes: true, attributeFilter: ['data-reduce-motion'] })
    return () => observer.disconnect()
  }, [])

  return <MotionConfig reducedMotion={reduced ? 'always' : 'user'}>{children}</MotionConfig>
}
