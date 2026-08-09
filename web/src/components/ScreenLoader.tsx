/* A reel of leader spinning while the projectionist threads the next
   thing: circle, crosshair, a sweeping hand. The global reduced-motion
   rules freeze the sweep to a still frame, which still reads as film
   leader rather than a broken spinner. */
export function ScreenLoader() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-ink">
      <div className="relative h-16 w-16" aria-hidden>
        <svg viewBox="0 0 64 64" className="absolute inset-0 h-full w-full">
          <circle
            cx="32"
            cy="32"
            r="29"
            fill="none"
            stroke="var(--color-line)"
            strokeWidth="1.5"
          />
          <circle
            cx="32"
            cy="32"
            r="19"
            fill="none"
            stroke="var(--color-line)"
            strokeWidth="1"
          />
          <path d="M0 32h64M32 0v64" stroke="var(--color-line)" strokeWidth="1" />
        </svg>
        <svg
          viewBox="0 0 64 64"
          className="absolute inset-0 h-full w-full animate-[wd-sweep_1.2s_linear_infinite]"
        >
          <path d="M32 32V4" stroke="var(--color-ember)" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>
      <p className="font-mono text-[11px] tracking-[0.3em] text-muted uppercase">Rolling</p>
    </div>
  )
}
