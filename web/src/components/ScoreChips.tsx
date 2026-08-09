import { motion } from 'motion/react'

/* Rating sources, shown with their own mark and linked back to where the
   number came from. A score with no way to check it is just a number we
   are asking people to trust. */

type Props = {
  name: string
  type: string
  tmdbId: number
  imdbId?: string | null
  imdb: number | null
  rt: number | null
  metacritic: number | null
  tmdb: number | null
}

/* Rotten Tomatoes calls 60 and above Fresh, below that Rotten, and the two
   have different marks: a tomato and a splat. */
const FRESH_AT = 60
/* Metacritic bands its own scores: green from 61, yellow from 40, red below. */
const MC_GOOD = 61
const MC_MIXED = 40

function Imdb() {
  return (
    <svg viewBox="0 0 64 32" className="h-4 w-8" aria-hidden focusable="false">
      <rect width="64" height="32" rx="5" fill="#f5c518" />
      <g fill="#000">
        <rect x="7" y="9" width="4" height="14" />
        <path d="M14 9h6l1.6 7L23 9h6v14h-4v-8l-1.8 8h-2.6L19 15v8h-5z" />
        <path d="M32 9h5.6c2.6 0 3.4 1 3.4 3v8c0 2-.8 3-3.4 3H32zm4 3v8h.8c.7 0 1-.2 1-1v-6c0-.8-.3-1-1-1z" />
        <path d="M43 9h4v4.6c.5-.6 1.2-1 2.1-1 1.7 0 2.4 1 2.4 2.8v4.8c0 1.8-.7 2.8-2.4 2.8-.9 0-1.6-.4-2.1-1V23h-4zm4 6.4v4.2c0 .5.2.7.6.7s.5-.2.5-.7v-4.2c0-.5-.1-.7-.5-.7s-.6.2-.6.7z" />
      </g>
    </svg>
  )
}

function Tomato({ fresh }: { fresh: boolean }) {
  if (fresh) {
    return (
      <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden focusable="false">
        <circle cx="12" cy="14" r="8" fill="#fa320a" />
        <path d="M12 6c-1.6-2.2-4-2.6-5.4-1.8 1 1.6 2.6 2.6 4 2.8-.6-1.4-.4-2.6.2-3.4.8 1 1.2 2.2 1.2 2.4z" fill="#3f9e4d" />
        <path d="M12 6c1.6-2.2 4-2.6 5.4-1.8-1 1.6-2.6 2.6-4 2.8" fill="#3f9e4d" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden focusable="false">
      <path
        d="M12 4c1 2 3 1 3.6 2.6.6 1.6 2.8 1 3 2.8.2 1.6-1.4 2-1 3.4.4 1.4 2 2.4 1 3.6-1 1.2-2.6.2-3.6 1.2-1 1-.6 2.8-2.2 2.8s-1.2-1.8-2.2-2.8c-1-1-2.6 0-3.6-1.2-1-1.2.6-2.2 1-3.6.4-1.4-1.2-1.8-1-3.4.2-1.8 2.4-1.2 3-2.8C10.6 5 11 6 12 4z"
        fill="#0ac855"
      />
      <circle cx="12" cy="12" r="3" fill="#08a745" />
    </svg>
  )
}

function Metacritic({ tone }: { tone: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden focusable="false">
      <circle cx="12" cy="12" r="11" fill={tone} />
      <path d="M7 17V7h3l2 5 2-5h3v10h-2.6v-5.6L12.8 15h-1.6L9.6 11.4V17z" fill="#fff" />
    </svg>
  )
}

function Tmdb() {
  return (
    <svg viewBox="0 0 64 32" className="h-4 w-8" aria-hidden focusable="false">
      <defs>
        <linearGradient id="tmdb-mark" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#90cea1" />
          <stop offset="100%" stopColor="#01b4e4" />
        </linearGradient>
      </defs>
      <rect width="64" height="32" rx="5" fill="url(#tmdb-mark)" />
      <text
        x="32"
        y="22"
        textAnchor="middle"
        fontFamily="Helvetica, Arial, sans-serif"
        fontSize="14"
        fontWeight="700"
        fill="#0d253f"
      >
        TMDB
      </text>
    </svg>
  )
}

function Chip({
  href,
  mark,
  value,
  caption,
  title,
}: {
  href: string
  mark: React.ReactNode
  value: string
  caption: string
  title: string
}) {
  return (
    <motion.a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 400, damping: 28 }}
      title={title}
      className="wd-plate wd-plate--hover group flex items-center gap-2 px-3 py-1.5"
    >
      {mark}
      <span className="flex flex-col leading-none">
        <span className="font-mono text-sm text-fg">{value}</span>
        <span className="mt-0.5 text-[10px] text-muted transition-colors group-hover:text-ember">
          {caption}
        </span>
      </span>
    </motion.a>
  )
}

export function ScoreChips({ name, type, tmdbId, imdbId, imdb, rt, metacritic, tmdb }: Props) {
  const search = encodeURIComponent(name)
  const chips = []

  if (imdb != null) {
    chips.push(
      <Chip
        key="imdb"
        // Without the id there is still an honest destination: a search.
        href={imdbId ? `https://www.imdb.com/title/${imdbId}/` : `https://www.imdb.com/find/?q=${search}`}
        mark={<Imdb />}
        value={imdb.toFixed(1)}
        caption="out of 10"
        title={`${name} on IMDb`}
      />,
    )
  }
  if (rt != null) {
    chips.push(
      <Chip
        key="rt"
        href={`https://www.rottentomatoes.com/search?search=${search}`}
        mark={<Tomato fresh={rt >= FRESH_AT} />}
        value={`${rt}%`}
        caption={rt >= FRESH_AT ? 'fresh' : 'rotten'}
        title={`${name} on Rotten Tomatoes`}
      />,
    )
  }
  if (metacritic != null) {
    const tone = metacritic >= MC_GOOD ? '#3f9e6a' : metacritic >= MC_MIXED ? '#c07a1e' : '#c0392b'
    chips.push(
      <Chip
        key="mc"
        href={`https://www.metacritic.com/search/${search}/`}
        mark={<Metacritic tone={tone} />}
        value={String(metacritic)}
        caption="metascore"
        title={`${name} on Metacritic`}
      />,
    )
  }
  if (tmdb != null) {
    chips.push(
      <Chip
        key="tmdb"
        href={`https://www.themoviedb.org/${type}/${tmdbId}`}
        mark={<Tmdb />}
        value={tmdb.toFixed(1)}
        caption="out of 10"
        title={`${name} on TMDB`}
      />,
    )
  }

  if (chips.length === 0) return null
  return <div className="flex flex-wrap gap-2">{chips}</div>
}
