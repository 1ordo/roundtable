import { motion } from 'motion/react'
import clsx from 'clsx'
import { useMe } from '../app/useMe'
import { useUpdateProfile } from '../api/tracking'

const CULTURES = [
  { code: 'ar', name: 'Arabic' },
  { code: 'en', name: 'English' },
  { code: 'fr', name: 'French' },
  { code: 'es', name: 'Spanish' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'hi', name: 'Hindi' },
  { code: 'tr', name: 'Turkish' },
  { code: 'it', name: 'Italian' },
  { code: 'de', name: 'German' },
  { code: 'fa', name: 'Persian' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'zh', name: 'Chinese' },
  { code: 'ru', name: 'Russian' },
]

const GENRES = [
  { id: 28, name: 'Action' },
  { id: 35, name: 'Comedy' },
  { id: 18, name: 'Drama' },
  { id: 27, name: 'Horror' },
  { id: 878, name: 'Science fiction' },
  { id: 10749, name: 'Romance' },
  { id: 53, name: 'Thriller' },
  { id: 16, name: 'Animation' },
  { id: 9648, name: 'Mystery' },
  { id: 80, name: 'Crime' },
  { id: 12, name: 'Adventure' },
  { id: 14, name: 'Fantasy' },
  { id: 99, name: 'Documentary' },
  { id: 36, name: 'History' },
]

function Chip({
  active,
  onClick,
  tone = 'ember',
  children,
}: {
  active: boolean
  onClick: () => void
  tone?: 'ember' | 'nitrate'
  children: React.ReactNode
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      aria-pressed={active}
      className={clsx(
        'rounded-full border px-3.5 py-1.5 text-sm transition-colors',
        !active && 'border-line text-muted hover:text-fg',
        active &&
          (tone === 'nitrate'
            ? 'border-nitrate bg-nitrate/15 text-nitrate'
            : 'border-ember bg-ember/15 text-ember'),
      )}
    >
      {children}
    </motion.button>
  )
}

export function LanguagesSection() {
  const { data: me } = useMe()
  const update = useUpdateProfile()
  const languages = me?.user.prefs?.languages ?? []
  const genres = me?.user.prefs?.genres ?? []
  const parentsGuide = Boolean(me?.user.prefs?.parents_guide)

  function toggleLanguage(code: string) {
    const next = languages.includes(code)
      ? languages.filter((c) => c !== code)
      : [...languages, code]
    update.mutate({ languages: next })
  }

  function toggleGenre(id: number) {
    const next = genres.includes(id) ? genres.filter((g) => g !== id) : [...genres, id]
    update.mutate({ genres: next })
  }

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">What you like</h2>
      <p className="mt-1 text-sm text-muted">
        A starting point for the algorithm. It keeps learning from everything you watch,
        rate, like, and skip, so these matter most at the beginning.
      </p>

      <p className="wd-eyebrow mt-5">Cinema cultures and languages</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {CULTURES.map((c) => (
          <Chip
            key={c.code}
            active={languages.includes(c.code)}
            onClick={() => toggleLanguage(c.code)}
            tone="nitrate"
          >
            {c.name}
          </Chip>
        ))}
      </div>

      <p className="wd-eyebrow mt-6">Favourite genres</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {GENRES.map((g) => (
          <Chip key={g.id} active={genres.includes(g.id)} onClick={() => toggleGenre(g.id)}>
            {g.name}
          </Chip>
        ))}
      </div>

      <div className="wd-plate mt-8 flex items-center gap-4 px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm">Parents guide</p>
          <p className="mt-0.5 text-xs text-muted">
            Show the official age rating on every poster, and the full certification
            breakdown on each title page.
          </p>
        </div>
        <button
          role="switch"
          aria-checked={parentsGuide}
          aria-label="Parents guide"
          onClick={() => update.mutate({ parents_guide: !parentsGuide })}
          className={clsx(
            'relative h-6 w-11 shrink-0 rounded-full transition-colors',
            parentsGuide ? 'bg-ember' : 'bg-panel-2',
          )}
        >
          <motion.span
            layout
            transition={{ type: 'spring', stiffness: 600, damping: 40 }}
            className={clsx(
              'absolute top-0.5 h-5 w-5 rounded-full',
              parentsGuide ? 'right-0.5 bg-ink' : 'left-0.5 bg-muted',
            )}
          />
        </button>
      </div>
    </section>
  )
}
