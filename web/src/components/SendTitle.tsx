import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { useFriends } from '../api/social'

/* "Have you seen this" is most of what anyone sends, so it belongs on the
   title rather than only in the message thread. Friends only, the same rule
   as the rest of messaging. */
export function SendTitle({
  type,
  tmdbId,
  name,
}: {
  type: string
  tmdbId: number
  name: string
}) {
  const { data } = useFriends()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [sentTo, setSentTo] = useState<string[]>([])

  const friends = (data?.friends ?? []).filter((f) => f.handle)

  const send = useMutation({
    mutationFn: (handle: string) =>
      api.post(`/api/messages/${handle}`, {
        body: note.trim() || `Have you seen ${name}?`,
        type,
        tmdb_id: tmdbId,
      }),
    onSuccess: (_result, handle) => {
      setSentTo((current) => [...current, handle])
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
    },
  })

  if (friends.length === 0) return null

  return (
    <div className="relative">
      <motion.button
        whileTap={{ scale: 0.97 }}
        onClick={() => setOpen((current) => !current)}
        className={clsx(
          'rounded-[4px] border px-3.5 py-2.5 text-sm transition-colors',
          open
            ? 'border-ember text-ember'
            : 'border-line bg-panel text-muted hover:border-ember hover:text-ember',
        )}
      >
        Send to a friend
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
            className="wd-plate absolute top-full left-0 z-30 mt-2 w-72 p-3 shadow-xl shadow-black/40"
          >
            <input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={`Have you seen ${name}?`}
              className="w-full rounded-[4px] border border-line bg-panel-2 px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
            />
            <div className="wd-scroller mt-2 max-h-56 overflow-y-auto">
              {friends.map((friend) => {
                const done = sentTo.includes(friend.handle as string)
                return (
                  <button
                    key={friend.handle}
                    onClick={() => !done && send.mutate(friend.handle as string)}
                    disabled={done || send.isPending}
                    className="flex w-full items-center gap-2.5 rounded-[4px] px-2 py-2 text-left transition-colors hover:bg-panel-2 disabled:opacity-60"
                  >
                    {friend.avatar_path ? (
                      <img
                        src={friend.avatar_path}
                        alt=""
                        className="h-7 w-7 shrink-0 rounded-full object-cover"
                      />
                    ) : (
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-panel-2 text-[10px] text-ember">
                        {(friend.display_name || friend.username).slice(0, 1).toUpperCase()}
                      </span>
                    )}
                    <span className="min-w-0 flex-1 truncate text-sm">
                      {friend.display_name || `@${friend.handle}`}
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-muted">
                      {done ? 'sent' : 'send'}
                    </span>
                  </button>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
