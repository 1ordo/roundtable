import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'

type Result = {
  logged: number
  already_counted: number
  skipped: number
  times: number
}

/* "I have seen all of these" is not the same as "add one viewing to each".
 *
 * The endpoint tops every part up to a target rather than incrementing, so
 * the part you already logged is left alone. Pressing it again raises the
 * target by one, which is how you say you have been round the whole thing
 * twice. The label says which of the two is about to happen, because a
 * button that silently means something different the second time is how
 * people end up with a history they do not trust. */
export function WatchedWholeFranchise({
  collectionId,
  rounds = 0,
  compact = false,
}: {
  collectionId: number
  /** Complete times through so far, from times_all_watched. */
  rounds?: number
  compact?: boolean
}) {
  const queryClient = useQueryClient()
  const [done, setDone] = useState<Result | null>(null)
  const [target, setTarget] = useState(rounds + 1)

  const mark = useMutation({
    mutationFn: (times: number) =>
      api.post<Result>(`/api/collections/${collectionId}/watched`, { times }),
    onSuccess: (result) => {
      setDone(result)
      setTarget(result.times + 1)
      // The history, the shelves and this franchise all just changed.
      queryClient.invalidateQueries({ queryKey: ['next-up'] })
      queryClient.invalidateQueries({ queryKey: ['collection', String(collectionId)] })
      queryClient.invalidateQueries({ queryKey: ['history'] })
      queryClient.invalidateQueries({ queryKey: ['home'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  const seenOnce = target > 1
  const label = mark.isPending
    ? 'Logging'
    : seenOnce
      ? `Seen it all ${target} times`
      : 'I have seen all of these'

  return (
    /* Relative, with the confirmation absolutely placed under the button.
       Rendered in flow it grew the row it sits in, which shunted the
       neighbouring button upward and left the two misaligned. */
    <div className={clsx('relative', compact ? '' : 'mt-4')}>
      <motion.button
        whileTap={{ scale: 0.97 }}
        disabled={mark.isPending}
        onClick={() => mark.mutate(target)}
        title={
          seenOnce
            ? `Log a further round, bringing every part to ${target}`
            : 'Log every part you have not already logged. Nothing you have logged is counted twice.'
        }
        className={clsx(
          'rounded-[4px] border px-3.5 py-2 transition-colors disabled:opacity-50',
          compact ? 'text-xs' : 'text-sm',
          seenOnce
            ? 'border-ember/50 text-ember hover:bg-ember/10'
            : 'border-line bg-panel text-muted hover:border-ember hover:text-ember',
        )}
      >
        {label}
      </motion.button>

      <AnimatePresence>
        {done && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute top-full left-0 z-10 mt-1.5 w-max max-w-[16rem] text-xs text-muted"
          >
            {done.logged === 0
              ? 'Already all logged, so nothing changed.'
              : `Logged ${done.logged} ${done.logged === 1 ? 'viewing' : 'viewings'}.`}
            {done.already_counted > 0 && ` ${done.already_counted} were already counted.`}
            {done.skipped > 0 && ` ${done.skipped} not in the catalog yet.`}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}
