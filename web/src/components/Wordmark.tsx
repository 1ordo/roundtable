import clsx from 'clsx'

/* The mark is one lens drawn twice: an ember pass and a nitrate pass a
   couple of points out of register, the way a two-strip print fringes
   when the strips drift. One shape, two colors — the whole identity. */
export function BeamMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={clsx('h-8 w-8', className)} aria-hidden>
      <circle
        cx="14.8"
        cy="17.2"
        r="9.5"
        fill="none"
        stroke="var(--color-ember)"
        strokeWidth="2.4"
      />
      <circle
        cx="17.2"
        cy="14.8"
        r="9.5"
        fill="none"
        stroke="var(--color-nitrate)"
        strokeWidth="2.4"
        opacity="0.9"
      />
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={clsx(
        'font-display font-semibold tracking-[0.08em] text-fg uppercase',
        className,
      )}
    >
      Watchpile
    </span>
  )
}
