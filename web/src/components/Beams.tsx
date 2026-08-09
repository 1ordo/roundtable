import { motion } from 'motion/react'

/* The projector beams: one ember pass, one nitrate pass, crossing the
   room from opposite corners the way a two-strip print layers its dyes.
   All color comes from the tokens, so the beams follow any retheme. */
export function Beams() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: [0.5, 0.75, 0.5] }}
        transition={{ duration: 9, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute -top-1/4 -left-1/4 h-[150%] w-[150%]"
        style={{
          background:
            'conic-gradient(from 118deg at 0% 0%, transparent 0deg, color-mix(in srgb, var(--color-ember) 16%, transparent) 8deg, color-mix(in srgb, var(--color-ember) 5%, transparent) 22deg, transparent 32deg)',
        }}
      />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: [0.55, 0.35, 0.55] }}
        transition={{ duration: 11, repeat: Infinity, ease: 'easeInOut', delay: 1.2 }}
        className="absolute -top-1/4 -right-1/4 h-[150%] w-[150%]"
        style={{
          background:
            'conic-gradient(from 208deg at 100% 0%, transparent 0deg, color-mix(in srgb, var(--color-nitrate) 5%, transparent) 8deg, color-mix(in srgb, var(--color-nitrate) 14%, transparent) 22deg, transparent 32deg)',
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 110%, color-mix(in srgb, var(--color-ink) 90%, transparent), transparent)',
        }}
      />
    </div>
  )
}
