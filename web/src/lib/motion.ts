/* Whether to animate at all. Two sources: the operating system setting and
   the in-app one, either of which is enough to stop motion. Read at call
   time rather than cached, because the setting can change mid-session. */
export function motionOff(): boolean {
  return (
    window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
    document.documentElement.dataset.reduceMotion === 'true'
  )
}
