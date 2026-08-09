import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Link } from 'react-router'
import { img } from '../api/catalog'
import clsx from 'clsx'

export type DayTitle = {
  tmdb_id: number
  type: string
  name: string
  poster_path: string | null
  year: number | null
  rating_10: number | null
  loved: boolean
}

export type DayCount = {
  day: string
  count: number
  names: string[]
  titles: DayTitle[]
}

/* A year of watching, one square per day.
 *
 * Five steps of one hue, light to dark, because this is magnitude rather
 * than identity: a rainbow here would imply the colours mean different
 * things. Empty days get the panel colour rather than the lightest step, so
 * "nothing" never reads as "a little". */
/* Empty stays the panel colour of whichever theme is live; heat mixes
   toward ember so the ramp reads on soot and on silver alike. */
const STEPS = [
  'var(--color-panel-2)',
  'color-mix(in srgb, var(--color-ember) 30%, var(--color-panel-2))',
  'color-mix(in srgb, var(--color-ember) 55%, var(--color-panel-2))',
  'color-mix(in srgb, var(--color-ember) 78%, var(--color-panel-2))',
  'var(--color-ember)',
]
const DAY_LABELS = ['Mon', '', 'Wed', '', 'Fri', '', '']

function stepFor(count: number, busiest: number): string {
  if (count <= 0) return STEPS[0]
  if (busiest <= 1) return STEPS[4]
  // Four bands over the range, so a quiet year still shows contrast rather
  // than one flat colour.
  const ratio = count / busiest
  if (ratio <= 0.25) return STEPS[1]
  if (ratio <= 0.5) return STEPS[2]
  if (ratio <= 0.75) return STEPS[3]
  return STEPS[4]
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10)
}

/** The Monday on or before 1 January, so every column is a full week. */
function gridStart(year: number): Date {
  const first = new Date(Date.UTC(year, 0, 1))
  const weekday = (first.getUTCDay() + 6) % 7 // Monday is 0
  first.setUTCDate(first.getUTCDate() - weekday)
  return first
}

export function YearGrid({
  days,
  years,
  totalLabel = 'watched',
}: {
  days: DayCount[]
  years: number[]
  totalLabel?: string
}) {
  const thisYear = new Date().getFullYear()
  const available = years.length > 0 ? years : [thisYear]
  const [year, setYear] = useState(available[0])
  const [hover, setHover] = useState<DayCount | null>(null)
  // Hover previews, click pins. Two states rather than one, so moving the
  // mouse away does not close what you deliberately opened.
  const [picked, setPicked] = useState<DayCount | null>(null)

  const byDay = useMemo(() => {
    const map = new Map<string, DayCount>()
    for (const entry of days) map.set(entry.day, entry)
    return map
  }, [days])

  const weeks = useMemo(() => {
    const start = gridStart(year)
    const out: { day: string; inYear: boolean }[][] = []
    const cursor = new Date(start)
    // 53 columns covers every year including the ones that need a 53rd week.
    for (let week = 0; week < 53; week += 1) {
      const column: { day: string; inYear: boolean }[] = []
      for (let d = 0; d < 7; d += 1) {
        column.push({
          day: isoDay(cursor),
          inYear: cursor.getUTCFullYear() === year,
        })
        cursor.setUTCDate(cursor.getUTCDate() + 1)
      }
      out.push(column)
    }
    return out
  }, [year])

  const inYear = days.filter((d) => d.day.startsWith(String(year)))
  const total = inYear.reduce((sum, d) => sum + d.count, 0)
  const busiest = Math.max(1, ...inYear.map((d) => d.count))
  const activeDays = inYear.length

  // Month labels sit above the first column whose week contains the 1st.
  const monthLabels = useMemo(() => {
    const labels: { index: number; name: string }[] = []
    let lastMonth = -1
    weeks.forEach((column, index) => {
      const first = column.find((c) => c.inYear)
      if (!first) return
      const month = new Date(first.day + 'T00:00:00Z').getUTCMonth()
      if (month !== lastMonth) {
        lastMonth = month
        labels.push({
          index,
          name: new Date(Date.UTC(2000, month, 1)).toLocaleString(undefined, { month: 'short' }),
        })
      }
    })
    return labels
  }, [weeks])

  return (
    <section className="mt-10 min-w-0">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
            {year} in days
          </h2>
          <p className="mt-1 text-sm text-muted">
            {total} {totalLabel} across {activeDays} {activeDays === 1 ? 'day' : 'days'}
          </p>
        </div>
        {available.length > 1 && (
          <div className="wd-scroller flex gap-1 overflow-x-auto rounded-md border border-line bg-panel p-1">
            {available.map((option) => (
              <button
                key={option}
                onClick={() => setYear(option)}
                className={clsx(
                  'relative shrink-0 rounded-[4px] px-3 py-1 font-mono text-xs transition-colors',
                  year === option ? 'text-ink' : 'text-muted hover:text-fg',
                )}
              >
                {year === option && (
                  <motion.span
                    layoutId="year-grid-pill"
                    className="absolute inset-0 rounded-[4px] bg-ember"
                    transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                  />
                )}
                <span className="relative">{option}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="wd-scroller mt-5 overflow-x-auto pb-2">
        <div className="inline-block min-w-max">
          <div className="flex gap-[3px] pl-9">
            {weeks.map((_, index) => {
              const label = monthLabels.find((m) => m.index === index)
              return (
                <span key={index} className="w-[11px] font-mono text-[9px] text-muted">
                  {label?.name ?? ''}
                </span>
              )
            })}
          </div>

          <div className="mt-1 flex gap-[3px]">
            <div className="flex w-8 flex-col gap-[3px] pr-1">
              {DAY_LABELS.map((label, i) => (
                <span
                  key={i}
                  className="flex h-[11px] items-center justify-end font-mono text-[9px] text-muted"
                >
                  {label}
                </span>
              ))}
            </div>
            {weeks.map((column, wi) => (
              <div key={wi} className="flex flex-col gap-[3px]">
                {column.map((cell) => {
                  const entry = byDay.get(cell.day)
                  const count = cell.inYear ? (entry?.count ?? 0) : 0
                  return (
                    <button
                      key={cell.day}
                      onMouseEnter={() => entry && cell.inYear && setHover(entry)}
                      onFocus={() => entry && cell.inYear && setHover(entry)}
                      onMouseLeave={() => setHover(null)}
                      onBlur={() => setHover(null)}
                      onClick={() =>
                        entry && cell.inYear
                          ? setPicked(picked?.day === entry.day ? null : entry)
                          : undefined
                      }
                      aria-label={
                        cell.inYear
                          ? `${cell.day}: ${count} ${count === 1 ? 'title' : 'titles'}`
                          : undefined
                      }
                      tabIndex={cell.inYear && count > 0 ? 0 : -1}
                      className={clsx(
                        'h-[11px] w-[11px] rounded-[2px] transition-transform',
                        cell.inYear ? 'hover:scale-125' : 'opacity-25',
                        count > 0 && 'cursor-pointer',
                        picked?.day === cell.day && 'ring-2 ring-fg ring-offset-1 ring-offset-ink',
                      )}
                      style={{ backgroundColor: cell.inYear ? stepFor(count, busiest) : STEPS[0] }}
                    />
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {picked && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="wd-plate mt-4 p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-display text-base">
                  {new Date(picked.day + 'T00:00:00Z').toLocaleDateString(undefined, {
                    weekday: 'long',
                    day: 'numeric',
                    month: 'long',
                    year: 'numeric',
                  })}
                </p>
                <button
                  onClick={() => setPicked(null)}
                  className="font-mono text-[11px] text-muted transition-colors hover:text-fg"
                >
                  close
                </button>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-5 md:grid-cols-8">
                {picked.titles.map((title) => (
                  <Link
                    key={`${title.type}-${title.tmdb_id}`}
                    to={`/app/title/${title.type}/${title.tmdb_id}`}
                    className="group min-w-0"
                  >
                    {title.poster_path ? (
                      <img
                        src={img(title.poster_path, 'w185') ?? ''}
                        alt={title.name}
                        loading="lazy"
                        className="aspect-[2/3] w-full rounded-md border border-line object-cover transition-colors group-hover:border-ember"
                      />
                    ) : (
                      <span className="flex aspect-[2/3] w-full items-center justify-center rounded-md border border-line bg-panel-2 p-1 text-center text-[10px] text-muted">
                        {title.name}
                      </span>
                    )}
                    <span className="mt-1.5 block truncate text-xs">{title.name}</span>
                    <span className="flex items-center gap-1.5 font-mono text-[10px] text-muted">
                      {title.rating_10 != null && <span>{title.rating_10}/10</span>}
                      {title.loved && <span className="text-ember">loved</span>}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        {/* The hovered day, held in place so the tooltip never covers the
            grid it describes. */}
        <div className="min-h-[2.5rem] min-w-0 flex-1">
          {hover ? (
            <div>
              <p className="font-mono text-xs text-fg">
                {new Date(hover.day + 'T00:00:00Z').toLocaleDateString(undefined, {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
                <span className="ml-2 text-ember">
                  {hover.count} {hover.count === 1 ? 'title' : 'titles'}
                </span>
              </p>
              <p className="mt-0.5 truncate text-xs text-muted">{hover.names.join(', ')}</p>
            </div>
          ) : (
            <p className="text-xs text-muted">
              Hover a day to see what you watched, click it for the artwork.
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="font-mono text-[10px] text-muted">Less</span>
          {STEPS.map((step) => (
            <span
              key={step}
              className="h-[11px] w-[11px] rounded-[2px]"
              style={{ backgroundColor: step }}
            />
          ))}
          <span className="font-mono text-[10px] text-muted">More</span>
        </div>
      </div>
    </section>
  )
}
