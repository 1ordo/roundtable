import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { motion } from 'motion/react'
import clsx from 'clsx'
import {
  isNotConfigured,
  useBrowse,
  useForYou,
  useGenres,
  type BrowseSort,
  type BrowseType,
} from '../api/catalog'
import { useMe } from '../app/useMe'
import { PosterCard } from '../components/PosterCard'
import { Row } from '../components/Row'
import { LoadError, SetupNotice } from '../components/SetupNotice'

const TYPES: { key: BrowseType; label: string }[] = [
  { key: 'all', label: 'Everything' },
  { key: 'movie', label: 'Films' },
  { key: 'tv', label: 'Series' },
]

const SORTS: { key: BrowseSort; label: string }[] = [
  { key: 'popular', label: 'Popular' },
  { key: 'top', label: 'Top rated' },
  { key: 'new', label: 'Newest' },
]

function Segmented<T extends string>({
  options,
  value,
  onChange,
  layoutId,
}: {
  options: { key: T; label: string }[]
  value: T
  onChange: (next: T) => void
  layoutId: string
}) {
  return (
    <div className="flex rounded-[4px] border border-line bg-panel p-1">
      {options.map((option) => (
        <button
          key={option.key}
          onClick={() => onChange(option.key)}
          className={clsx(
            'relative rounded-[4px] px-3.5 py-1.5 text-sm transition-colors sm:px-4',
            value === option.key ? 'text-ink' : 'text-muted hover:text-fg',
          )}
        >
          {value === option.key && (
            <motion.span
              layoutId={layoutId}
              className="absolute inset-0 rounded-[4px] bg-ember"
              transition={{ type: 'spring', stiffness: 500, damping: 40 }}
            />
          )}
          <span className="relative">{option.label}</span>
        </button>
      ))}
    </div>
  )
}

const TITLES: Record<BrowseType, string> = {
  all: 'Browse',
  movie: 'Films',
  tv: 'Series',
}

/* Categories the genre list has no word for. Someone looking for K-drama is
   not looking for "Drama", and no combination of genre chips gets them there,
   because what they mean is where it is from. The label changes with the
   media type where the common name does: Korean films are not K-drama. */
const ORIGINS: { code: string; label: string; only?: BrowseType }[] = [
  { code: 'ko', label: 'K-drama', only: 'tv' },
  { code: 'ko', label: 'Korean' },
  { code: 'ja', label: 'Anime', only: 'tv' },
  { code: 'ja', label: 'Japanese' },
  { code: 'tr', label: 'Turkish' },
  { code: 'zh', label: 'Chinese' },
  { code: 'hi', label: 'Indian' },
  { code: 'ar', label: 'Arabic' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'it', label: 'Italian' },
  { code: 'de', label: 'German' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'th', label: 'Thai' },
  { code: 'sv', label: 'Swedish' },
]

function originsFor(type: BrowseType) {
  // On a series page "Anime" replaces "Japanese" rather than joining it.
  const named = new Set(ORIGINS.filter((o) => o.only === type).map((o) => o.code))
  return ORIGINS.filter((o) => (o.only ? o.only === type : !named.has(o.code)))
}

const ALL_OF_IT: Record<BrowseType, string> = {
  all: 'Everything',
  movie: 'Every film',
  tv: 'Every series',
}

/* The shelves this page opens on, before you have asked it for anything.
   They come from the same taste vector as the home page but built only from
   this kind of thing, so Series gets series suggestions rather than the home
   page with the films taken out. */
function ForYou({ media }: { media: BrowseType }) {
  const { data } = useForYou(media)
  const rows = data?.rows ?? []
  if (rows.length === 0) return null
  return (
    <div className="mt-8 flex flex-col gap-10">
      {rows.map((row) => (
        <Row key={row.key} title={row.title} items={row.items} shelf={row.key} media={media} />
      ))}
    </div>
  )
}

export function Browse() {
  const { data: me } = useMe()
  const { media } = useParams()
  const navigate = useNavigate()
  /* The route owns the media type when there is one, so Films and Series
     are real pages that can be linked, bookmarked and reloaded. */
  const routeType = media === 'movie' || media === 'tv' ? (media as BrowseType) : null
  const [type, setType] = useState<BrowseType>(routeType ?? 'all')
  /* The preference arrives with the profile query, which is usually still
     in flight on first render, so it cannot seed useState. Apply it once
     when it lands and never again, or every refetch would yank the toggle
     back out from under whoever just changed it. It never overrides a type
     the URL already asked for. */
  const seeded = useRef(false)
  const storedType = me?.user?.prefs?.default_type as BrowseType | undefined
  useEffect(() => {
    if (seeded.current || !storedType || routeType) return
    seeded.current = true
    setType(storedType)
  }, [storedType, routeType])
  useEffect(() => {
    if (routeType) setType(routeType)
  }, [routeType])
  const [genre, setGenre] = useState<string | null>(null)
  const [language, setLanguage] = useState<string | null>(null)
  const [sort, setSort] = useState<BrowseSort>('popular')
  const [page, setPage] = useState(1)
  const { data: genres } = useGenres()
  const { data, error, isLoading } = useBrowse(type, genre, sort, page, language)

  const combined = genres?.combined ?? []
  /* A genre only appears if the current type actually has it upstream:
     series have no Horror, films have no Reality. The label stays selected
     across a type switch whenever both sides know it. */
  const available = combined.filter((g) =>
    type === 'all'
      ? g.movie_ids.length || g.tv_ids.length
      : type === 'movie'
        ? g.movie_ids.length
        : g.tv_ids.length,
  )
  const orphaned = genre !== null && !available.some((g) => g.name === genre)

  function switchType(next: BrowseType) {
    setType(next)
    setPage(1)
    // Keep the address honest: the toggle and the sidebar are the same
    // navigation, so switching type moves to that type's page.
    navigate(next === 'all' ? '/app/browse' : `/app/browse/${next}`, { replace: true })
    // Keep the filter if the new side knows it, drop it if it does not.
    const entry = combined.find((g) => g.name === genre)
    const keeps =
      entry &&
      (next === 'all'
        ? entry.movie_ids.length || entry.tv_ids.length
        : next === 'movie'
          ? entry.movie_ids.length
          : entry.tv_ids.length)
    if (!keeps) setGenre(null)
  }

  return (
    <div>
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="wd-eyebrow">Explore</p>
          <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
            {TITLES[type]}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented options={TYPES} value={type} onChange={switchType} layoutId="browse-type" />
          <Segmented
            options={SORTS}
            value={sort}
            onChange={(next) => {
              setSort(next)
              setPage(1)
            }}
            layoutId="browse-sort"
          />
        </div>
      </header>

      {/* Only while they are still looking rather than searching. The moment
          a genre or a sort is chosen, this page is a grid of that answer and
          a screen of shelves above it is in the way. */}
      {genre === null && language === null && sort === 'popular' && page === 1 && (
        <ForYou media={type} />
      )}

      <h2 className="mt-12 font-display text-2xl font-semibold uppercase tracking-[0.02em]">
        {ALL_OF_IT[type]}
      </h2>

      <div className="mt-6 flex flex-wrap gap-2">
        <button
          onClick={() => {
            setGenre(null)
            setPage(1)
          }}
          className={clsx(
            'rounded-full border px-3.5 py-1.5 text-sm transition-colors',
            genre === null
              ? 'border-ember bg-ember/15 text-ember'
              : 'border-line text-muted hover:text-fg',
          )}
        >
          Any genre
        </button>
        {available.map((g) => (
          <button
            key={g.name}
            onClick={() => {
              setGenre(g.name)
              setPage(1)
            }}
            className={clsx(
              'rounded-full border px-3.5 py-1.5 text-sm transition-colors',
              genre === g.name
                ? 'border-ember bg-ember/15 text-ember'
                : 'border-line text-muted hover:text-fg',
            )}
          >
            {g.name}
          </button>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => {
            setLanguage(null)
            setPage(1)
          }}
          className={clsx(
            'rounded-full border px-3.5 py-1.5 text-sm transition-colors',
            language === null
              ? 'border-nitrate bg-nitrate/15 text-nitrate'
              : 'border-line text-muted hover:text-fg',
          )}
        >
          Anywhere
        </button>
        {originsFor(type).map((origin) => (
          <button
            key={`${origin.code}-${origin.label}`}
            onClick={() => {
              setLanguage(origin.code)
              setPage(1)
            }}
            className={clsx(
              'rounded-full border px-3.5 py-1.5 text-sm transition-colors',
              language === origin.code
                ? 'border-nitrate bg-nitrate/15 text-nitrate'
                : 'border-line text-muted hover:text-fg',
            )}
          >
            {origin.label}
          </button>
        ))}
      </div>

      {orphaned && (
        <p className="mt-4 text-sm text-muted">
          {type === 'tv' ? 'Series' : 'Films'} do not use the {genre} genre, so the filter was
          cleared.
        </p>
      )}

      {error && (
        <div className="mt-8">{isNotConfigured(error) ? <SetupNotice /> : <LoadError />}</div>
      )}

      {data && data.results.length === 0 && !isLoading && (
        <p className="mt-10 text-center text-sm text-muted">
          Nothing matches that yet. Try another genre or sort.
        </p>
      )}

      <div className="mt-8 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {isLoading &&
          !data &&
          [...Array(12)].map((_, i) => (
            <div key={i} className="aspect-[2/3] animate-pulse rounded-lg bg-panel" />
          ))}
        {data?.results.map((title, i) => (
          <div key={`${title.type}-${title.tmdb_id}`} className="[&>div]:w-full">
            <PosterCard title={title} index={i % 12} />
          </div>
        ))}
      </div>

      {data && data.total_pages > 1 && (
        <div className="mt-10 flex items-center justify-center gap-4">
          <button
            onClick={() => {
              setPage((p) => Math.max(1, p - 1))
              window.scrollTo({ top: 0 })
            }}
            disabled={page <= 1}
            className="rounded-[4px] border border-line bg-panel px-6 py-2.5 text-sm transition-colors hover:border-ember hover:text-ember disabled:opacity-40 disabled:hover:border-line disabled:hover:text-fg"
          >
            Previous
          </button>
          <span className="font-mono text-xs text-muted">
            {data.page} / {Math.min(data.total_pages, 500)}
          </span>
          <button
            onClick={() => {
              setPage((p) => p + 1)
              window.scrollTo({ top: 0 })
            }}
            disabled={data.page >= data.total_pages}
            className="rounded-[4px] border border-line bg-panel px-6 py-2.5 text-sm transition-colors hover:border-ember hover:text-ember disabled:opacity-40 disabled:hover:border-line disabled:hover:text-fg"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
