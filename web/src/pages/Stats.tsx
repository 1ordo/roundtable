import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { motion } from 'motion/react'
import clsx from 'clsx'
import { useMe } from '../app/useMe'
import {
  BarList,
  PeopleGrid,
  SERIES,
  TitleGrid,
  TopTen,
  languageName,
  type NameCount,
  type PersonCount,
  type TitleHighlight,
} from '../components/StatsViews'
import { StatsCards } from '../components/StatsCards'
import { api } from '../api/client'
import { img } from '../api/catalog'
import { YearGrid, type DayCount } from '../components/YearGrid'

/* Chart marks use validated chart tokens (OKLCH band, chroma, CVD, contrast
   all pass on the panel surface); text stays in text tokens. */
const CHART_EMBER = '#c9532a'

type Stats = {
  totals: {
    watched: number
    hours: number
    loved: number
    rated: number
    avg_rating: number | null
    this_year: number
  }
  genres: { name: string; count: number }[]
  monthly: { month: string; count: number }[]
  ratings: { month: string; count: number }[]
  top_actors: { name: string; count: number; extra: string | null }[]
  people: PersonCount[]
  directors: PersonCount[]
  languages: NameCount[]
  decades: NameCount[]
  highest_rated: TitleHighlight[]
  recent: TitleHighlight[]
  by_year: NameCount[]
  days: DayCount[]
  years: number[]
  top_ten: TitleHighlight[]
  longest: TitleHighlight[]
  collections: NameCount[]
  runtime_buckets: NameCount[]
  streak_longest: number
  wrap: {
    year: number
    watched: number
    hours: number
    favorite: string | null
    top_genre: string | null
  }
}

function useStats() {
  return useQuery({ queryKey: ['stats'], queryFn: () => api.get<Stats>('/api/stats') })
}

function Tile({ label, value, index }: { label: string; value: string; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="wd-plate p-5"
    >
      <p className="font-mono text-3xl font-medium text-fg">{value}</p>
      <p className="mt-1 text-xs text-muted">{label}</p>
    </motion.div>
  )
}

function MonthLabel({ month }: { month: string }) {
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const part = Number(month.split('-')[1] ?? 1)
  return <>{names[part - 1]}</>
}

function ColumnChart({
  data,
  labelFor,
  ariaLabel,
}: {
  data: { key: string; label: React.ReactNode; count: number; tooltip: string }[]
  labelFor?: (d: { key: string; count: number }) => string
  ariaLabel: string
}) {
  const max = Math.max(1, ...data.map((d) => d.count))
  return (
    <div>
      <div className="flex h-40 items-end gap-1.5" role="img" aria-label={ariaLabel}>
        {data.map((d, i) => (
          <div key={d.key} className="group relative flex h-full flex-1 flex-col justify-end">
            <div className="pointer-events-none absolute -top-8 left-1/2 z-10 -translate-x-1/2 rounded-md border border-line bg-panel-2 px-2 py-1 font-mono text-[10px] whitespace-nowrap text-fg opacity-0 transition-opacity group-hover:opacity-100">
              {d.tooltip}
            </div>
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: `${Math.max(d.count > 0 ? 4 : 1, (d.count / max) * 100)}%` }}
              transition={{ delay: 0.15 + i * 0.03, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="w-full rounded-t-[4px]"
              style={{ backgroundColor: d.count > 0 ? CHART_EMBER : 'var(--color-panel-2)' }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-1.5">
        {data.map((d) => (
          <p key={d.key} className="flex-1 text-center font-mono text-[10px] text-muted">
            {d.label}
          </p>
        ))}
      </div>
      <details className="mt-2">
        <summary className="cursor-pointer font-mono text-[10px] text-muted">
          View the numbers
        </summary>
        <table className="mt-2 w-full text-left font-mono text-xs text-muted">
          <tbody>
            {data.map((d) => (
              <tr key={d.key}>
                <td className="py-0.5">{labelFor ? labelFor(d) : d.key}</td>
                <td className="text-fg">{d.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

type View = 'overview' | 'people' | 'titles'

const VIEWS: { key: View; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'people', label: 'People' },
  { key: 'titles', label: 'Titles' },
]

export function StatsPage() {
  const { data } = useStats()
  const { data: me } = useMe()
  const [view, setView] = useState<View>('overview')
  if (!data) return null
  const { totals, wrap } = data
  const maxGenre = Math.max(1, ...data.genres.map((g) => g.count))

  return (
    <div className="min-w-0 max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="wd-eyebrow">Your shelf</p>
          <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
            Stats
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted">Your watching, measured.</p>
        </div>
        <div className="flex rounded-md border border-line bg-panel p-1">
          {VIEWS.map((option) => (
            <button
              key={option.key}
              onClick={() => setView(option.key)}
              className={clsx(
                'relative rounded-[4px] px-4 py-1.5 text-sm transition-colors',
                view === option.key ? 'text-ink' : 'text-muted hover:text-fg',
              )}
            >
              {view === option.key && (
                <motion.span
                  layoutId="stats-view"
                  className="absolute inset-0 rounded-[4px] bg-ember"
                  transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                />
              )}
              <span className="relative">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <Tile label="watched" value={String(totals.watched)} index={0} />
        <Tile label="hours" value={String(totals.hours)} index={1} />
        <Tile label="loved" value={String(totals.loved)} index={2} />
        <Tile
          label="average rating"
          value={totals.avg_rating != null ? String(totals.avg_rating) : 'none yet'}
          index={3}
        />
        <Tile label="longest daily streak" value={String(data.streak_longest)} index={4} />
      </div>

      {view === 'overview' && (
        <>
          {/* A year at a glance goes first: it is the thing people actually
              want to look at, and the thing worth showing someone else. */}
          <YearGrid days={data.days ?? []} years={data.years ?? []} />

          <section className="mt-10">
            <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
              Last twelve months
            </h2>
            <div className="wd-plate mt-4 p-5">
              <ColumnChart
                ariaLabel="Titles watched per month over the last twelve months"
                data={data.monthly.map((m) => ({
                  key: m.month,
                  label: <MonthLabel month={m.month} />,
                  count: m.count,
                  tooltip: `${m.month}: ${m.count} watched`,
                }))}
                labelFor={(d) => d.key}
              />
            </div>
          </section>

          <section className="mt-10">
            <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
              Top genres
            </h2>
            <div className="wd-plate mt-4 flex flex-col gap-2.5 p-5">
              {data.genres.length === 0 && (
                <p className="text-sm text-muted">Watch something and the picture forms here.</p>
              )}
              {data.genres.map((genre, i) => (
                <div key={genre.name} className="flex items-center gap-3">
                  <p className="w-28 shrink-0 truncate text-sm text-fg">{genre.name}</p>
                  <div className="h-3 flex-1">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(genre.count / maxGenre) * 100}%` }}
                      transition={{
                        delay: 0.1 + i * 0.05,
                        duration: 0.5,
                        ease: [0.22, 1, 0.36, 1],
                      }}
                      className="h-full rounded-r-[4px]"
                      style={{ backgroundColor: CHART_EMBER }}
                    />
                  </div>
                  <p className="w-8 shrink-0 text-right font-mono text-xs text-muted">
                    {genre.count}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-10">
            <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
              How you rate
            </h2>
            <div className="wd-plate mt-4 p-5">
              <ColumnChart
                ariaLabel="Count of titles per rating from one to ten"
                data={data.ratings.map((r) => ({
                  key: r.month,
                  label: r.month,
                  count: r.count,
                  tooltip: `rated ${r.month}/10: ${r.count}`,
                }))}
                labelFor={(d) => `${d.key}/10`}
              />
            </div>
          </section>

          {data.top_actors.length > 0 && (
            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
                Faces you keep watching
              </h2>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {data.top_actors.map((actor, i) => (
                  <motion.div
                    key={actor.name}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05, duration: 0.35 }}
                    className="wd-plate flex items-center gap-3 px-3 py-2"
                  >
                    {actor.extra ? (
                      <img
                        src={img(actor.extra, 'w185') ?? ''}
                        alt=""
                        className="h-9 w-9 rounded-full object-cover"
                      />
                    ) : (
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-panel-2 font-display text-sm text-muted">
                        {actor.name.slice(0, 1)}
                      </span>
                    )}
                    <span className="flex-1 truncate text-sm">{actor.name}</span>
                    <span className="font-mono text-xs text-muted">{actor.count}x</span>
                  </motion.div>
                ))}
              </div>
            </section>
          )}

          <section className="mt-10">
            <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
              Your {wrap.year} so far
            </h2>
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="mt-4 rounded-lg p-px"
              style={{
                background: 'linear-gradient(120deg, var(--color-ember), var(--color-nitrate))',
              }}
            >
              <div className="rounded-[7px] bg-ink p-8">
                <p className="wd-eyebrow">Roundtable wrap</p>
                <p className="mt-4 font-display text-5xl font-medium">
                  {wrap.watched} <span className="text-xl text-muted">titles</span>
                </p>
                <p className="mt-2 font-display text-3xl">
                  {wrap.hours} <span className="text-lg text-muted">hours in the dark</span>
                </p>
                {wrap.favorite && (
                  <p className="mt-4 text-sm text-muted">
                    Highlight of the year: <span className="text-fg">{wrap.favorite}</span>
                  </p>
                )}
                {wrap.top_genre && (
                  <p className="mt-1 text-sm text-muted">
                    Home genre: <span className="text-fg">{wrap.top_genre}</span>
                  </p>
                )}
                <p className="mt-6 font-mono text-[10px] text-muted">
                  Screenshot this card to share it.
                </p>
              </div>
            </motion.div>
          </section>
          <section className="mt-10 grid gap-8 md:grid-cols-2">
            <div className="min-w-0">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
                Languages you watch in
              </h2>
              <BarList rows={data.languages} color={SERIES[1]} translate={languageName} />
              {data.languages.length === 0 && (
                <p className="mt-3 text-sm text-muted">Nothing logged yet.</p>
              )}
            </div>
            <div className="min-w-0">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
                Decades
              </h2>
              <BarList rows={data.decades} color={SERIES[2]} />
              {data.decades.length === 0 && (
                <p className="mt-3 text-sm text-muted">Nothing logged yet.</p>
              )}
            </div>
          </section>

          {data.runtime_buckets.length > 0 && (
            <section className="mt-10 min-w-0">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
                How long you sit for
              </h2>
              <BarList rows={data.runtime_buckets} color={SERIES[3]} />
            </section>
          )}
        </>
      )}

      {view === 'people' && (
        <>
          <PeopleGrid people={data.people} label="Actors you watch most" />
          <PeopleGrid people={data.directors} label="Directors you watch most" />
          {data.collections.length > 0 && (
            <section className="mt-10 min-w-0">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
                Franchises you went through
              </h2>
              <p className="mt-1 text-sm text-muted">More than one part, so it was a run.</p>
              <BarList rows={data.collections} color={SERIES[2]} />
            </section>
          )}
          {data.people.length === 0 && (
            <p className="mt-10 text-muted">
              Log a few watches and the faces behind them show up here.
            </p>
          )}
        </>
      )}

      {view === 'titles' && (
        <>
          <TitleGrid
            titles={data.highest_rated}
            label="Your highest rated"
            note="Ranked by what you gave them, with loved counting extra."
          />
          <TitleGrid titles={data.recent} label="Recently watched" />
          <TopTen titles={data.top_ten} />
          <TitleGrid
            titles={data.longest}
            label="The long ones"
            note="Where most of those hours went."
          />
          {data.recent.length === 0 && <p className="mt-10 text-muted">Nothing logged yet.</p>}
        </>
      )}

      <section className="mt-12 border-t border-line pt-8">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
          Share your year
        </h2>
        <p className="mt-1 text-sm text-muted">
          Four cards of {wrap.year}. Save one, or the whole set.
        </p>
        <StatsCards
          data={{
            username: me?.user.username ?? 'You',
            year: Number(wrap.year),
            watched: Number(wrap.watched ?? 0),
            hours: Number(wrap.hours ?? 0),
            loved: totals.loved,
            avgRating: totals.avg_rating,
            streak: data.streak_longest,
            topGenres: data.genres,
            topLanguages: data.languages,
            favorite: (wrap.favorite as string | null) ?? null,
            people: data.people,
            highest: data.highest_rated,
            decades: data.decades,
          }}
        />
      </section>
    </div>
  )
}
