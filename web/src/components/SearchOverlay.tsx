import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Link, useNavigate } from 'react-router'
import { img, useSearch } from '../api/catalog'
import { usePeopleSearch, nameOf } from '../api/social2'

/* Search as a panel over whatever you were doing, rather than a page you
 * navigate to and then have to navigate back from.
 *
 * Escape closes it, clicking outside closes it, and picking a result closes
 * it and takes you there. It never changes the address on open, so leaving
 * really does put you back exactly where you were.
 */
export function SearchOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [term, setTerm] = useState('')
  const [debounced, setDebounced] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const { data: titles, isFetching } = useSearch(debounced)
  const { data: people } = usePeopleSearch(debounced)

  // A ref, not the state setter, or the timer resets on every render.
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setDebounced(term), 220)
    return () => window.clearTimeout(timer.current)
  }, [term])

  useEffect(() => {
    if (!open) return
    // Focus after the entrance, or the browser scrolls the page to it.
    const id = window.setTimeout(() => inputRef.current?.focus(), 60)
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(id)
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  useEffect(() => {
    if (!open) setTerm('')
  }, [open])

  function go(to: string) {
    onClose()
    navigate(to)
  }

  const results = titles?.results ?? []
  const persons = people ?? []
  const nothing =
    debounced.trim().length >= 2 && !isFetching && results.length === 0 && persons.length === 0

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-start justify-center bg-ink/80 px-4 pt-[10vh] backdrop-blur-sm"
        >
          <motion.div
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Search"
            className="w-full max-w-2xl overflow-hidden rounded-[8px] border border-line bg-panel shadow-2xl shadow-black/50"
          >
            <div className="flex items-center gap-3 border-b border-line px-4">
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4 shrink-0 text-muted"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden
              >
                <path d="M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm9.5 16-4.4-4.4" />
              </svg>
              <input
                ref={inputRef}
                value={term}
                onChange={(event) => setTerm(event.target.value)}
                placeholder="Films, series, people"
                className="wd-bare min-w-0 flex-1 bg-transparent py-4 text-base placeholder:text-muted"
              />
              <kbd className="shrink-0 rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted">
                esc
              </kbd>
            </div>

            <div className="wd-scroller max-h-[60vh] overflow-y-auto">
              {persons.length > 0 && (
                <div className="px-2 pt-3">
                  <p className="wd-eyebrow px-2">People</p>
                  {persons.map((person) => (
                    <button
                      key={person.handle ?? person.username}
                      onClick={() => person.handle && go(`/app/u/${person.handle}`)}
                      className="flex w-full items-center gap-3 rounded-[4px] px-2 py-2 text-left transition-colors hover:bg-panel-2"
                    >
                      {person.avatar_path ? (
                        <img
                          src={person.avatar_path}
                          alt=""
                          className="h-8 w-8 shrink-0 rounded-full object-cover"
                        />
                      ) : (
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-panel-2 text-xs text-ember">
                          {nameOf(person).replace('@', '').slice(0, 1).toUpperCase()}
                        </span>
                      )}
                      <span className="min-w-0">
                        <span className="block truncate text-sm">{nameOf(person)}</span>
                        {person.handle && (
                          <span className="block font-mono text-[11px] text-muted">
                            @{person.handle}
                          </span>
                        )}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {results.length > 0 && (
                <div className="px-2 pt-3 pb-2">
                  <p className="wd-eyebrow px-2">Titles</p>
                  {results.slice(0, 10).map((result) => (
                    <button
                      key={`${result.type}-${result.tmdb_id}`}
                      onClick={() => go(`/app/title/${result.type}/${result.tmdb_id}`)}
                      className="flex w-full items-center gap-3 rounded-[4px] px-2 py-2 text-left transition-colors hover:bg-panel-2"
                    >
                      {result.poster_path ? (
                        <img
                          src={img(result.poster_path, 'w185') ?? ''}
                          alt=""
                          loading="lazy"
                          className="h-14 w-10 shrink-0 rounded object-cover"
                        />
                      ) : (
                        <span className="h-14 w-10 shrink-0 rounded bg-panel-2" />
                      )}
                      <span className="min-w-0">
                        <span className="block truncate text-sm">{result.name}</span>
                        <span className="block font-mono text-[11px] text-muted">
                          {result.type === 'tv' ? 'Series' : 'Film'} {result.year ?? ''}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {nothing && (
                <p className="px-4 py-8 text-center text-sm text-muted">
                  Nothing matching that. Try fewer words.
                </p>
              )}

              {debounced.trim().length < 2 && (
                <div className="px-4 py-6">
                  <p className="text-sm text-muted">
                    Search the catalog, or find someone by their handle.
                  </p>
                  <Link
                    to="/app/ask"
                    onClick={onClose}
                    className="mt-3 inline-block text-sm text-ember hover:underline"
                  >
                    Or describe what you are in the mood for
                  </Link>
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/* The bar that opens it. Not an input: tapping anywhere on it opens the
   real one, so there is never a moment where you are typing into a box that
   is about to be replaced. */
export function SearchBar({ onOpen }: { onOpen: () => void }) {
  return (
    /* Translucent, because it sits over artwork. The blur plus a dark scrim
       is what keeps the label readable whether the poster behind it is a
       night sky or a snowfield: tinting the text to the backdrop is not
       something CSS can do reliably, so the bar carries its own contrast
       instead of hoping the image cooperates. */
    <button
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-[6px] border border-fg/15 bg-ink/55 px-4 py-2.5 text-left text-sm text-fg/70 shadow-md shadow-black/10 backdrop-blur-xl transition-colors hover:border-ember/60 hover:text-fg"
    >
      <svg
        viewBox="0 0 24 24"
        className="h-4 w-4 shrink-0"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden
      >
        <path d="M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm9.5 16-4.4-4.4" />
      </svg>
      {/* The blurred, tinted bar is the contrast; a text shadow on top
          smeared the label on the light theme. */}
      <span className="flex-1">
        Search films, series and people
      </span>
      <kbd className="hidden rounded border border-fg/15 px-1.5 py-0.5 font-mono text-[10px] sm:block">
        /
      </kbd>
    </button>
  )
}
