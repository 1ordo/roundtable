import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { Link } from 'react-router'
import clsx from 'clsx'
import { img } from '../api/catalog'

export type Step = { key: string; label: string; detail: string }
export type Considered = {
  tmdb_id: number
  type: string
  name: string
  year: number | null
  poster_path: string | null
}

/* What the assistant is actually doing, rather than the word "Thinking".
 *
 * Each line appears only once the work it describes has finished, so this is
 * a report and not a progress animation pretending to be one. The last line
 * is the one worth reading: it says how many of the titles the model named
 * survived being checked against the catalog. */
export function ChatTrace({
  steps,
  considered,
  running,
  collapsible = false,
}: {
  steps: Step[]
  considered: Considered[]
  running: boolean
  collapsible?: boolean
}) {
  const [open, setOpen] = useState(!collapsible)
  if (steps.length === 0 && !running) return null

  return (
    <div className="rounded-md border border-line bg-panel/60 p-3">
      <button
        onClick={() => collapsible && setOpen(!open)}
        className={clsx(
          'flex w-full items-center gap-2 text-left',
          collapsible ? 'cursor-pointer' : 'cursor-default',
        )}
      >
        <span
          aria-hidden
          className={clsx(
            'h-1.5 w-1.5 shrink-0 rounded-full',
            running ? 'animate-pulse bg-nitrate' : 'bg-muted',
          )}
        />
        <span className="font-mono text-[10px] tracking-[0.2em] text-muted uppercase">
          {running ? 'Working' : `${steps.length} steps`}
        </span>
        {collapsible && (
          <span className="ml-auto font-mono text-[10px] text-muted">
            {open ? 'hide' : 'show'}
          </span>
        )}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <ol className="mt-2.5 flex flex-col gap-1.5">
              <AnimatePresence initial={false}>
                {steps.map((step) => (
                  <motion.li
                    key={step.key}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.25, ease: 'easeOut' }}
                    className="flex flex-wrap items-baseline gap-x-2 font-mono text-[11px]"
                  >
                    <span aria-hidden className="text-nitrate">
                      &rsaquo;
                    </span>
                    <span className="text-fg/85">{step.label}</span>
                    <span className="text-muted">{step.detail}</span>
                  </motion.li>
                ))}
              </AnimatePresence>
              {running && (
                <motion.li
                  initial={{ opacity: 0 }}
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1.4, repeat: Infinity }}
                  className="flex items-baseline gap-2 font-mono text-[11px] text-muted"
                >
                  <span aria-hidden className="text-nitrate">
                    &rsaquo;
                  </span>
                  working
                </motion.li>
              )}
            </ol>

            {considered.length > 0 && (
              <div className="mt-3">
                <p className="wd-eyebrow wd-eyebrow--nitrate">Considering</p>
                <div className="wd-scroller mt-2 flex gap-2 overflow-x-auto pb-1">
                  {considered.map((title) => (
                    <Link
                      key={`${title.type}-${title.tmdb_id}`}
                      to={`/app/title/${title.type}/${title.tmdb_id}`}
                      title={`${title.name}${title.year ? ` (${title.year})` : ''}`}
                      className="shrink-0"
                    >
                      {title.poster_path ? (
                        <img
                          src={img(title.poster_path, 'w185') ?? ''}
                          alt={title.name}
                          loading="lazy"
                          className="h-16 w-11 rounded object-cover opacity-60 transition-opacity hover:opacity-100"
                        />
                      ) : (
                        <span className="flex h-16 w-11 items-center justify-center rounded bg-panel-2 p-1 text-center text-[8px] text-muted">
                          {title.name}
                        </span>
                      )}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
