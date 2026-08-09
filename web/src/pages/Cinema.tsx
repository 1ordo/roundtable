import { motion } from 'motion/react'
import { Link } from 'react-router'
import { useUpdateProfile } from '../api/tracking'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { img, type TitleCard } from '../api/catalog'
import { useMe } from '../app/useMe'

type CinemaTitle = {
  card: TitleCard
  opens_on: string | null
  in_cinemas_now: boolean
  tracked: boolean
  country: string | null
}

type CinemaPage = {
  country: string | null
  countries: string[]
  now_showing: CinemaTitle[]
  coming_soon: CinemaTitle[]
  tracking: CinemaTitle[]
  elsewhere: CinemaTitle[]
}

function flag(code: string): string {
  return code
    .toUpperCase()
    .replace(/./g, (char) => String.fromCodePoint(127397 + char.charCodeAt(0)))
}

function useCinema() {
  return useQuery({
    queryKey: ['cinema'],
    queryFn: () => api.get<CinemaPage>('/api/cinema'),
    staleTime: 10 * 60_000,
  })
}

function useTrack() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ tmdb_id, tracked }: { tmdb_id: number; tracked: boolean }) =>
      tracked
        ? api.delete(`/api/cinema/track?type=movie&tmdb_id=${tmdb_id}`)
        : api.post('/api/cinema/track', { type: 'movie', tmdb_id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cinema'] }),
  })
}

function opensText(entry: CinemaTitle): string | null {
  if (entry.in_cinemas_now) return 'In cinemas now'
  if (!entry.opens_on) return null
  const when = new Date(`${entry.opens_on}T00:00:00`)
  const days = Math.ceil((when.getTime() - Date.now()) / 86_400_000)
  if (days < 0) return null
  if (days === 0) return 'Opens today'
  if (days === 1) return 'Opens tomorrow'
  if (days < 14) return `Opens in ${days} days`
  return `Opens ${when.toLocaleDateString(undefined, { day: 'numeric', month: 'long' })}`
}

function Ticket({
  entry,
  index,
  showCountry,
}: {
  entry: CinemaTitle
  index: number
  showCountry: boolean
}) {
  const track = useTrack()
  const when = opensText(entry)

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.4), duration: 0.35 }}
      className="min-w-0"
    >
      <Link to={`/app/title/movie/${entry.card.tmdb_id}`} className="group block">
        <span className="relative block">
          {entry.card.poster_path ? (
            <img
              src={img(entry.card.poster_path, 'w342') ?? ''}
              alt={entry.card.name}
              loading="lazy"
              className="aspect-[2/3] w-full rounded-lg border border-line object-cover transition-colors group-hover:border-ember"
            />
          ) : (
            <span className="flex aspect-[2/3] w-full items-center justify-center rounded-lg border border-line bg-panel-2 p-2 text-center text-xs text-muted">
              {entry.card.name}
            </span>
          )}
          {entry.in_cinemas_now && (
            <span className="absolute top-2 left-2 rounded bg-ember px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink">
              NOW
            </span>
          )}
          {/* Only worth saying when more than one country is in play. */}
          {showCountry && entry.country && (
            <span
              className="absolute top-2 right-2 rounded bg-ink/80 px-1.5 py-0.5 text-[11px] backdrop-blur"
              title={entry.country}
            >
              {flag(entry.country)}
            </span>
          )}
          {/* The shelves cannot help here: a film only in cinemas is kept
              out of them on purpose. So this page is where the fit gets
              said, and what is on now is ordered by it. */}
          {entry.card.match != null && (
            <span
              title={`${entry.card.match}% match for you`}
              className={clsx(
                'absolute bottom-2 left-2 rounded bg-ink/85 px-1.5 py-0.5 font-mono text-[10px] backdrop-blur',
                entry.card.match >= 70 ? 'text-ember' : 'text-muted',
              )}
            >
              {entry.card.match}%
            </span>
          )}
        </span>
        <span className="mt-2 block truncate text-sm">{entry.card.name}</span>
      </Link>

      {when && (
        <span
          className={clsx(
            'mt-0.5 block font-mono text-[11px]',
            entry.in_cinemas_now ? 'text-ember' : 'text-muted',
          )}
        >
          {when}
        </span>
      )}

      <motion.button
        whileTap={{ scale: 0.96 }}
        disabled={track.isPending}
        onClick={() => track.mutate({ tmdb_id: entry.card.tmdb_id, tracked: entry.tracked })}
        aria-pressed={entry.tracked}
        className={clsx(
          'mt-2 w-full rounded-[4px] border px-2 py-1.5 text-xs transition-colors disabled:opacity-50',
          entry.tracked
            ? 'border-ember bg-ember/15 text-ember'
            : 'border-line text-muted hover:border-ember hover:text-ember',
        )}
      >
        {/* A film already on cannot be "told when it opens": that day has
            been and gone. The label has to match the state. */}
        {entry.tracked
          ? entry.in_cinemas_now
            ? 'On your list'
            : 'Watching for it'
          : entry.in_cinemas_now
            ? 'Add to my list'
            : 'Tell me when it opens'}
      </motion.button>
    </motion.div>
  )
}

function Shelf({
  label,
  note,
  entries,
  showCountry = false,
}: {
  label: string
  note?: string
  entries: CinemaTitle[]
  showCountry?: boolean
}) {
  if (entries.length === 0) return null
  return (
    <section className="mt-10 min-w-0">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">{label}</h2>
      {note && <p className="mt-1 text-sm text-muted">{note}</p>}
      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {entries.map((entry, i) => (
          <Ticket key={entry.card.tmdb_id} entry={entry} index={i} showCountry={showCountry} />
        ))}
      </div>
    </section>
  )
}

const COUNTRY_NAMES: Record<string, string> = {
  EG: 'Egypt',
  BE: 'Belgium',
  MA: 'Morocco',
  FR: 'France',
  GB: 'United Kingdom',
  US: 'United States',
  DE: 'Germany',
  NL: 'Netherlands',
  ES: 'Spain',
  IT: 'Italy',
  AE: 'United Arab Emirates',
  SA: 'Saudi Arabia',
  TR: 'Turkey',
  CA: 'Canada',
}

function countryName(code: string): string {
  return COUNTRY_NAMES[code] ?? code
}

export function Cinema() {
  const update = useUpdateProfile()
  const { data, isLoading } = useCinema()
  const { data: me } = useMe()
  const countries = data?.countries ?? me?.user?.countries ?? []

  /* Removing one here writes straight to the profile, because the whole
     point is that the page you noticed the problem on is the page you fix
     it on. The primary country stays put; the rest are the extras. */
  function drop(code: string) {
    const primary = me?.user?.country_code
    const extras = countries.filter((c) => c !== code && c !== primary)
    if (code === primary) {
      const next = countries.find((c) => c !== code)
      if (next) update.mutate({ country_code: next, countries: extras.filter((c) => c !== next) })
      return
    }
    update.mutate({ countries: extras })
  }
  const several = countries.length > 1

  return (
    <div className="min-w-0">
      <header className="mb-8">
        <p className="wd-eyebrow">Tonight</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          In cinemas
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Track anything you want to see on a big screen and you will hear the day it opens.
        </p>

        {/* The countries in play, named and removable right here. Buried in
            settings, a stale list looks like the page showing countries you
            never asked for. */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="wd-eyebrow">Screens in</span>
          {countries.length === 0 && (
            <span className="text-sm text-muted">nowhere yet, add a country</span>
          )}
          {countries.map((code) => (
            <span
              key={code}
              className="flex items-center gap-1.5 rounded-full border border-line bg-panel py-1 pr-1.5 pl-3 text-xs"
            >
              {countryName(code)}
              {countries.length > 1 && (
                <button
                  onClick={() => drop(code)}
                  aria-label={`Stop following cinemas in ${countryName(code)}`}
                  className="flex h-4 w-4 items-center justify-center rounded-full text-muted transition-colors hover:bg-panel-2 hover:text-danger"
                >
                  &times;
                </button>
              )}
            </span>
          ))}
          <Link
            to="/app/settings"
            className="rounded-full border border-dashed border-line px-3 py-1 text-xs text-muted transition-colors hover:border-ember hover:text-ember"
          >
            Add
          </Link>
        </div>
      </header>

      {isLoading && (
        <div className="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="aspect-[2/3] animate-pulse rounded-lg bg-panel" />
          ))}
        </div>
      )}

      <Shelf
        label="You are waiting for"
        note="You get one alert the day each of these opens, not a reminder every week."
        entries={data?.tracking ?? []}
        showCountry={several}
      />
      <Shelf label="On now" entries={data?.now_showing ?? []} showCountry={several} />
      <Shelf label="Coming soon" entries={data?.coming_soon ?? []} showCountry={several} />
      <Shelf
        label="Out elsewhere"
        note="On release somewhere, with no date on file for your countries yet. Track one and you will hear if that changes."
        entries={data?.elsewhere ?? []}
      />

      {data &&
        data.now_showing.length === 0 &&
        data.coming_soon.length === 0 &&
        data.elsewhere.length === 0 &&
        data.tracking.length === 0 && (
          <p className="mt-10 text-sm text-muted">
            Nothing on file for your country yet. It fills in as the catalog updates.
          </p>
        )}
    </div>
  )
}
