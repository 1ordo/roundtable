import { motion } from 'motion/react'
import { Link } from 'react-router'
import { img } from '../api/catalog'

/* Categorical series colours (ember, nitrate, viola, brass), validated for
   both themes and for colour vision deficiency. Assigned in fixed order,
   never cycled. */
export const SERIES = ['#c9532a', '#3d9c88', '#8a6bd6', '#b0893a']

export type NameCount = { name: string; count: number; extra?: string | null }
export type PersonCount = {
  name: string
  count: number
  profile_path: string | null
  person_id: number | null
}
export type TitleHighlight = {
  tmdb_id: number
  type: string
  name: string
  poster_path: string | null
  year: number | null
  rating_10: number | null
  loved: boolean
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  ar: 'Arabic',
  fr: 'French',
  ja: 'Japanese',
  ko: 'Korean',
  es: 'Spanish',
  it: 'Italian',
  de: 'German',
  hi: 'Hindi',
  tr: 'Turkish',
  fa: 'Persian',
  pt: 'Portuguese',
  zh: 'Chinese',
  ru: 'Russian',
  sv: 'Swedish',
  da: 'Danish',
  nl: 'Dutch',
}

/* A ranked bar list. One series, so no legend: the heading names it, and
   every row is directly labelled. */
export function BarList({
  rows,
  color = SERIES[0],
  translate,
}: {
  rows: NameCount[]
  color?: string
  translate?: (name: string) => string
}) {
  if (rows.length === 0) return null
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <div className="mt-4 flex flex-col gap-2">
      {rows.map((row, i) => (
        <div key={row.name} className="flex items-center gap-3">
          <span className="w-32 shrink-0 truncate text-sm text-muted">
            {translate ? translate(row.name) : row.name}
          </span>
          <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-panel-2">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(row.count / max) * 100}%` }}
              transition={{ delay: Math.min(i * 0.04, 0.4), duration: 0.6, ease: 'easeOut' }}
              className="h-full rounded-full"
              style={{ backgroundColor: color }}
            />
          </div>
          <span className="w-8 shrink-0 text-right font-mono text-xs text-muted">{row.count}</span>
        </div>
      ))}
    </div>
  )
}

export function PeopleGrid({ people, label }: { people: PersonCount[]; label: string }) {
  if (people.length === 0) return null
  return (
    <section className="mt-10 min-w-0">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">{label}</h2>
      <div className="mt-4 grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-6">
        {people.map((person, i) => {
          const body = (
            <>
              {person.profile_path ? (
                <img
                  src={img(person.profile_path, 'w185') ?? ''}
                  alt={person.name}
                  loading="lazy"
                  className="aspect-square w-full rounded-full border border-line object-cover transition-colors group-hover:border-ember"
                />
              ) : (
                <div className="flex aspect-square w-full items-center justify-center rounded-full border border-line bg-panel-2 font-display text-xl text-muted">
                  {person.name.slice(0, 1)}
                </div>
              )}
              <p className="mt-2 truncate text-center text-sm">{person.name}</p>
              <p className="text-center font-mono text-[11px] text-muted">
                {person.count} {person.count === 1 ? 'title' : 'titles'}
              </p>
            </>
          )
          return (
            <motion.div
              key={person.name}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.04, 0.4), duration: 0.35 }}
              className="min-w-0"
            >
              {person.person_id ? (
                <Link to={`/app/person/${person.person_id}`} className="group block">
                  {body}
                </Link>
              ) : (
                <div className="group">{body}</div>
              )}
            </motion.div>
          )
        })}
      </div>
    </section>
  )
}

export function TitleGrid({
  titles,
  label,
  note,
}: {
  titles: TitleHighlight[]
  label: string
  note?: string
}) {
  if (titles.length === 0) return null
  return (
    <section className="mt-10 min-w-0">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">{label}</h2>
      {note && <p className="mt-1 text-sm text-muted">{note}</p>}
      <div className="mt-4 grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-6">
        {titles.map((title, i) => (
          <motion.div
            key={`${title.type}-${title.tmdb_id}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.04, 0.4), duration: 0.35 }}
            className="min-w-0"
          >
            <Link to={`/app/title/${title.type}/${title.tmdb_id}`} className="group block">
              {title.poster_path ? (
                <img
                  src={img(title.poster_path, 'w185') ?? ''}
                  alt={title.name}
                  loading="lazy"
                  className="aspect-[2/3] w-full rounded-md border border-line object-cover transition-colors group-hover:border-ember"
                />
              ) : (
                <div className="flex aspect-[2/3] w-full items-center justify-center rounded-md border border-line bg-panel-2 p-2 text-center text-xs text-muted">
                  {title.name}
                </div>
              )}
              <p className="mt-2 truncate text-sm">{title.name}</p>
              <p className="flex items-center gap-1.5 font-mono text-[11px] text-muted">
                {title.rating_10 != null && <span>{title.rating_10}/10</span>}
                {title.loved && <span className="text-ember">loved</span>}
                {title.year && <span>{title.year}</span>}
              </p>
            </Link>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

export function languageName(code: string): string {
  return LANGUAGE_NAMES[code] ?? code.toUpperCase()
}

/* A ranked ten with artwork. A numbered list of names says the same thing,
   but nobody recognises their own year in a list of names. */
export function TopTen({ titles }: { titles: TitleHighlight[] }) {
  if (titles.length === 0) return null
  return (
    <section className="mt-10 min-w-0">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
        Your top {titles.length}
      </h2>
      <p className="mt-1 text-sm text-muted">Rated highest, with anything you loved lifted.</p>
      <ol className="mt-4 flex flex-col gap-2">
        {titles.map((title, i) => (
          <motion.li
            key={`${title.type}-${title.tmdb_id}`}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: Math.min(i * 0.05, 0.5), duration: 0.35, ease: 'easeOut' }}
            className="min-w-0"
          >
            <Link
              to={`/app/title/${title.type}/${title.tmdb_id}`}
              className="wd-plate wd-plate--hover flex items-center gap-4 p-2.5"
            >
              <span className="w-7 shrink-0 text-center font-display text-2xl text-ember">
                {i + 1}
              </span>
              {title.poster_path ? (
                <img
                  src={img(title.poster_path, 'w185') ?? ''}
                  alt=""
                  loading="lazy"
                  className="h-20 w-14 shrink-0 rounded-md object-cover"
                />
              ) : (
                <span className="h-20 w-14 shrink-0 rounded-md bg-panel-2" />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{title.name}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-2 font-mono text-[11px] text-muted">
                  {title.year && <span>{title.year}</span>}
                  <span>{title.type === 'tv' ? 'Series' : 'Film'}</span>
                  {title.loved && <span className="text-ember">loved</span>}
                </span>
              </span>
              {title.rating_10 != null && (
                <span className="shrink-0 font-display text-xl text-fg">{title.rating_10}</span>
              )}
            </Link>
          </motion.li>
        ))}
      </ol>
    </section>
  )
}
