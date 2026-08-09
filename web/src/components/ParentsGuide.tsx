import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api, ApiError } from '../api/client'
import { useMe } from '../app/useMe'

type AdvisoryItem = { text: string; spoiler: boolean }

type Advisory = {
  categories: {
    key: string
    label: string
    severity: string
    note: string
    items?: AdvisoryItem[]
    total?: number
  }[]
  summary: string
  source?: string
}

const SEVERITY_STYLE: Record<string, string> = {
  severe: 'text-danger border-danger/50',
  moderate: 'text-ember border-ember/50',
  mild: 'text-nitrate border-nitrate/40',
  'none-reported': 'text-muted border-line',
}

const SEVERITY_LABEL: Record<string, string> = {
  severe: 'Strong',
  moderate: 'Moderate',
  mild: 'Mild',
  'none-reported': 'Nothing noted',
}

/* One category, expandable. IMDb entries are the point of this section:
   they say where the content is and how, which a severity word cannot. */
function Category({
  category,
  fromImdb,
}: {
  category: Advisory['categories'][number]
  fromImdb: boolean
}) {
  const [open, setOpen] = useState(false)
  const [spoilers, setSpoilers] = useState(false)
  const items = category.items ?? []
  const shown = spoilers ? items : items.filter((i) => !i.spoiler)
  const hidden = items.length - shown.length

  return (
    <div className="wd-plate overflow-hidden">
      <button
        onClick={() => items.length > 0 && setOpen(!open)}
        className={clsx(
          'flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5 text-left',
          items.length > 0 ? 'hover:bg-panel-2' : 'cursor-default',
        )}
      >
        <span className="min-w-52 text-sm">{category.label}</span>
        <span
          className={clsx(
            'rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase',
            SEVERITY_STYLE[category.severity] ?? SEVERITY_STYLE['none-reported'],
          )}
        >
          {SEVERITY_LABEL[category.severity] ?? category.severity}
        </span>
        {!open && category.note && (
          <span className="min-w-0 flex-1 truncate text-sm text-muted">{category.note}</span>
        )}
        {items.length > 0 && (
          <span className="ml-auto shrink-0 font-mono text-[11px] text-muted">
            {open ? 'hide' : `${category.total ?? items.length} details`}
          </span>
        )}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="overflow-hidden border-t border-line bg-panel-2"
          >
            <ul className="flex flex-col gap-2.5 px-4 py-3">
              {shown.map((item, i) => (
                <li key={i} className="flex gap-2.5 text-sm text-fg/90">
                  <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted" />
                  <span className="min-w-0">{item.text}</span>
                </li>
              ))}
              {hidden > 0 && (
                <li>
                  <button
                    onClick={() => setSpoilers(true)}
                    className="rounded-[4px] border border-line px-2.5 py-1 text-xs text-muted transition-colors hover:border-ember hover:text-ember"
                  >
                    Show {hidden} {hidden === 1 ? 'entry' : 'entries'} with spoilers
                  </button>
                </li>
              )}
              {fromImdb && (
                <li className="pt-1 text-[11px] text-muted">
                  Written by IMDb contributors who watched it.
                </li>
              )}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function ContentDetail({ type, tmdbId }: { type: string; tmdbId: number }) {
  const [asked, setAsked] = useState(false)
  const { data, error, isFetching } = useQuery({
    queryKey: ['advisory', type, tmdbId],
    queryFn: () => api.get<Advisory>(`/api/titles/${type}/${tmdbId}/advisory`),
    enabled: asked,
    staleTime: Infinity,
    retry: false,
  })
  const disabled = error instanceof ApiError && error.status === 503
  const fromImdb = data?.source === 'imdb'

  return (
    <div className="mt-6">
      {!asked && (
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={() => setAsked(true)}
          className="rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
        >
          What is in it?
        </motion.button>
      )}

      {isFetching && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.35, 1, 0.35] }}
          transition={{ duration: 1.4, repeat: Infinity }}
          className="wd-eyebrow"
        >
          Fetching the guide
        </motion.p>
      )}

      {disabled && (
        <p className="text-sm text-muted">
          This part needs the AI features, which are switched off.
        </p>
      )}
      {error && !disabled && (
        <p className="text-sm text-danger">Could not put that together. Try again shortly.</p>
      )}

      <AnimatePresence>
        {data && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="min-w-0"
          >
            {data.summary && <p className="max-w-2xl text-sm text-fg/90">{data.summary}</p>}
            <div className="mt-4 flex flex-col gap-2">
              {data.categories.map((category) => (
                <Category key={category.key} category={category} fromImdb={fromImdb} />
              ))}
            </div>
            {/* Which source this is matters more than any styling: the two
                make different claims and must never look identical. */}
            {fromImdb ? (
              <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                <span className="rounded bg-[#f5c518] px-1.5 py-0.5 font-mono text-[10px] font-bold text-black">
                  IMDb
                </span>
                From the IMDb parents guide. Open a category to read what happens and where.
              </p>
            ) : (
              <p className="mt-3 text-xs text-muted">
                No IMDb guide exists for this one, so this is worked out from the description,
                the genres and the official rating, not from having watched it. A category with
                nothing noted means no information, not that the content is absent.
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

const COUNTRY_NAMES: Record<string, string> = {
  US: 'United States',
  GB: 'United Kingdom',
  DE: 'Germany',
  FR: 'France',
  ES: 'Spain',
  IT: 'Italy',
  NL: 'Netherlands',
  EG: 'Egypt',
  MA: 'Morocco',
  AE: 'United Arab Emirates',
  SA: 'Saudi Arabia',
  TR: 'Turkey',
  CA: 'Canada',
  AU: 'Australia',
  BR: 'Brazil',
  IN: 'India',
  JP: 'Japan',
  KR: 'South Korea',
}

// Ratings that mean "adults only" wherever they are issued.
const STRONG = new Set(['R', 'NC-17', 'X', '18', '18+', 'TV-MA', 'R18+', '16', 'VM18'])

export function ParentsGuide({
  certifications,
  certification,
  type,
  tmdbId,
}: {
  certifications: Record<string, string>
  certification: string | null | undefined
  type: string
  tmdbId: number
}) {
  const { data: me } = useMe()
  const enabled = Boolean(me?.user.prefs?.parents_guide)
  if (!enabled) return null

  const entries = Object.entries(certifications ?? {}).sort(([a], [b]) => a.localeCompare(b))
  const country = me?.user.country_code

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="mt-10 min-w-0"
    >
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Parents guide</h2>

      {certification ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <span
            className="rounded-[4px] border px-3 py-1.5 font-mono text-lg"
            style={{
              borderColor: STRONG.has(certification)
                ? 'var(--color-danger)'
                : 'var(--color-line)',
              color: STRONG.has(certification) ? 'var(--color-danger)' : 'var(--color-fg)',
            }}
          >
            {certification}
          </span>
          <p className="text-sm text-muted">
            The official rating
            {country && certifications[country]
              ? ` in ${COUNTRY_NAMES[country] ?? country}`
              : ', from the closest country on file'}
            .
          </p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted">
          No official age rating is on file for this one. That means we do not know it, not
          that it is unrated.
        </p>
      )}

      {entries.length > 0 && (
        <>
          <p className="wd-eyebrow mt-6">
            Ratings elsewhere
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {entries.map(([code, rating]) => (
              <span
                key={code}
                className="rounded-[4px] border border-line bg-panel px-2.5 py-1 text-xs"
                title={COUNTRY_NAMES[code] ?? code}
              >
                <span className="font-mono text-muted">{code}</span>{' '}
                <span className="text-fg">{rating}</span>
              </span>
            ))}
          </div>
        </>
      )}

      <ContentDetail type={type} tmdbId={tmdbId} />
    </motion.section>
  )
}
