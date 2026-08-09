import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import clsx from 'clsx'
import { useSendSignal, useSignalState } from '../api/signals'
import {
  useAddToList,
  useLists,
  useMarkWatched,
  useRemoveFromList,
  useTitleState,
} from '../api/tracking'
import { SendTitle } from './SendTitle'

function Thumb({ down }: { down?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={down ? { transform: 'rotate(180deg)' } : undefined}
      aria-hidden
    >
      <path d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1h3Zm0 0 4-7a2.4 2.4 0 0 1 2.4 2.4V9H19a2 2 0 0 1 2 2.3l-1 6A2 2 0 0 1 18 19h-8a3 3 0 0 1-3-3" />
    </svg>
  )
}

function ActionButton({
  active,
  onClick,
  children,
  disabled,
}: {
  active?: boolean
  onClick: () => void
  children: React.ReactNode
  disabled?: boolean
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={clsx(
        'rounded-[4px] border px-4 py-2.5 text-sm transition-colors disabled:opacity-50',
        active
          ? 'border-ember bg-ember/15 text-ember'
          : 'border-line bg-panel text-fg hover:border-ember/60',
      )}
    >
      {children}
    </motion.button>
  )
}

export function TitleActions({
  type,
  tmdbId,
  name,
}: {
  type: 'movie' | 'tv'
  tmdbId: number
  name: string
}) {
  const { data: lists } = useLists()
  const { data: state } = useTitleState(type, tmdbId)
  const { data: signal } = useSignalState(type, tmdbId)
  const sendSignal = useSendSignal(type, tmdbId)
  const addToList = useAddToList(type, tmdbId)
  const removeFromList = useRemoveFromList(type, tmdbId)
  const markWatched = useMarkWatched(type, tmdbId)

  // Every click matters: opening a title is itself a signal.
  useEffect(() => {
    sendSignal.mutate('view')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, tmdbId])

  const [panelOpen, setPanelOpen] = useState(false)
  const [listsOpen, setListsOpen] = useState(false)
  const [rating, setRating] = useState<number | null>(null)
  const [loved, setLoved] = useState(false)

  const watchlist = lists?.lists.find((l) => l.kind === 'watchlist')
  const shared = lists?.lists.find((l) => l.kind === 'shared')
  /* Lists the person made themselves. The cinema list is created by the
     tracker rather than by them, so it is not offered here. */
  const custom = (lists?.lists ?? []).filter(
    (l) => l.kind !== 'watchlist' && l.kind !== 'shared' && l.kind !== 'cinema',
  )
  const inCustom = custom.filter((l) => state?.lists.includes(l.id)).length

  function toggle(listId: string | undefined) {
    if (!listId || !state) return
    if (state.lists.includes(listId)) removeFromList.mutate(listId)
    else addToList.mutate({ listId })
  }

  function submitWatched() {
    markWatched.mutate(
      { rating_10: rating ?? undefined, loved },
      {
        onSuccess: () => {
          setPanelOpen(false)
          setRating(null)
          setLoved(false)
        },
      },
    )
  }

  return (
    <div className="mt-6">
      <div className="flex flex-wrap gap-2.5">
        <ActionButton
          active={!!watchlist && state?.lists.includes(watchlist.id)}
          onClick={() => toggle(watchlist?.id)}
          disabled={!watchlist || !state}
        >
          {watchlist && state?.lists.includes(watchlist.id) ? 'On your watchlist' : 'Add to watchlist'}
        </ActionButton>
        <ActionButton
          active={!!shared && state?.lists.includes(shared.id)}
          onClick={() => toggle(shared?.id)}
          disabled={!shared || !state}
        >
          {shared && state?.lists.includes(shared.id) ? 'On your shared list' : 'Add to shared list'}
        </ActionButton>
        <SendTitle type={type} tmdbId={tmdbId} name={name} />

        <ActionButton active={panelOpen} onClick={() => setPanelOpen((open) => !open)}>
          {state && state.watched_count > 0
            ? `Watched ${state.watched_count}x, log again`
            : 'Mark watched'}
        </ActionButton>

        {/* Every list the person actually made. Without these a custom list
            can never receive anything, which made the whole feature dead. */}
        {custom.length > 0 && (
          <div className="relative">
            <ActionButton active={listsOpen} onClick={() => setListsOpen((open) => !open)}>
              {inCustom > 0 ? `In ${inCustom} of your lists` : 'Save to a list'}
            </ActionButton>
            <AnimatePresence>
              {listsOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.18, ease: 'easeOut' }}
                  className="wd-plate absolute top-full left-0 z-20 mt-2 max-h-72 w-64 overflow-y-auto p-1.5 shadow-xl shadow-black/40"
                >
                  {custom.map((list) => {
                    const on = state?.lists.includes(list.id) ?? false
                    return (
                      <button
                        key={list.id}
                        onClick={() => toggle(list.id)}
                        className="flex w-full items-center gap-2.5 rounded-[4px] px-2.5 py-2 text-left text-sm transition-colors hover:bg-panel-2"
                      >
                        <span
                          aria-hidden
                          className={clsx(
                            'flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                            on ? 'border-ember bg-ember text-ink' : 'border-line',
                          )}
                        >
                          {on && (
                            <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3">
                              <path d="M5 12l5 5L19 7" />
                            </svg>
                          )}
                        </span>
                        <span className="min-w-0 flex-1 truncate">{list.name}</span>
                        <span className="shrink-0 font-mono text-[10px] text-muted">
                          {list.count}
                        </span>
                      </button>
                    )
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        <div className="ml-1 flex items-center gap-1.5">
          <motion.button
            whileTap={{ scale: 1.25 }}
            onClick={() => sendSignal.mutate('like')}
            aria-pressed={signal?.liked ?? false}
            aria-label="More like this, please"
            title="More like this, please"
            className={clsx(
              'rounded-[4px] border p-2.5 transition-colors',
              signal?.liked
                ? 'border-ember bg-ember/15 text-ember'
                : 'border-line bg-panel text-muted hover:text-fg',
            )}
          >
            <Thumb />
          </motion.button>
          <motion.button
            whileTap={{ scale: 1.25 }}
            onClick={() => sendSignal.mutate('dislike')}
            aria-pressed={signal?.disliked ?? false}
            aria-label="Not for me"
            title="Not for me"
            className={clsx(
              'rounded-[4px] border p-2.5 transition-colors',
              signal?.disliked
                ? 'border-danger bg-danger/15 text-danger'
                : 'border-line bg-panel text-muted hover:text-fg',
            )}
          >
            <Thumb down />
          </motion.button>
        </div>
      </div>

      <AnimatePresence>
        {panelOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="wd-plate mt-3 max-w-md p-4">
              <p className="text-sm text-muted">How was it?</p>
              <div className="mt-3 flex items-center gap-1" role="radiogroup" aria-label="Rating">
                {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                  <button
                    key={n}
                    role="radio"
                    aria-checked={rating === n}
                    aria-label={`${n} out of 10`}
                    onClick={() => setRating(rating === n ? null : n)}
                    className={clsx(
                      'h-8 w-7 rounded-[4px] border font-mono text-xs transition-colors',
                      rating != null && n <= rating
                        ? 'border-ember bg-ember text-ink'
                        : 'border-line text-muted hover:border-ember/50',
                    )}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={loved}
                  onChange={(e) => setLoved(e.target.checked)}
                  className="accent-ember"
                />
                Loved it
              </label>
              <div className="mt-4 flex gap-2">
                <button
                  onClick={submitWatched}
                  disabled={markWatched.isPending}
                  className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
                >
                  Save to history
                </button>
                <button
                  onClick={() => setPanelOpen(false)}
                  className="rounded-[4px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:text-fg"
                >
                  Cancel
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
