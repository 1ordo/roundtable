import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useUpdateProfile } from '../api/tracking'
import { BeamMark } from './Wordmark'
import { TastePicker, TASTE_MINIMUM } from './TastePicker'

const COUNTRIES = [
  { code: 'EG', name: 'Egypt' },
  { code: 'MA', name: 'Morocco' },
  { code: 'AE', name: 'UAE' },
  { code: 'SA', name: 'Saudi Arabia' },
  { code: 'FR', name: 'France' },
  { code: 'DE', name: 'Germany' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'US', name: 'United States' },
  { code: 'ES', name: 'Spain' },
  { code: 'IT', name: 'Italy' },
  { code: 'TR', name: 'Turkey' },
  { code: 'NL', name: 'Netherlands' },
]

const CULTURES = [
  { code: 'ar', name: 'Arabic' },
  { code: 'en', name: 'English' },
  { code: 'fr', name: 'French' },
  { code: 'es', name: 'Spanish' },
  { code: 'tr', name: 'Turkish' },
  { code: 'ko', name: 'Korean' },
  { code: 'ja', name: 'Japanese' },
  { code: 'hi', name: 'Hindi' },
  { code: 'de', name: 'German' },
  { code: 'it', name: 'Italian' },
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
  { id: 14, name: 'Fantasy' },
  { id: 99, name: 'Documentary' },
]

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'rounded-full border px-3.5 py-1.5 text-sm transition-colors',
        active ? 'border-ember bg-ember/15 text-ember' : 'border-line text-muted hover:text-fg',
      )}
    >
      {children}
    </button>
  )
}

export function Onboarding() {
  const queryClient = useQueryClient()
  const updateProfile = useUpdateProfile()
  const [step, setStep] = useState(0)
  const [country, setCountry] = useState<string | null>(null)
  const [services, setServices] = useState<number[]>([])
  const [languages, setLanguages] = useState<string[]>([])
  const [genres, setGenres] = useState<number[]>([])
  const [liked, setLiked] = useState<{ type: string; tmdb_id: number }[]>([])
  const [problem, setProblem] = useState<string | null>(null)
  const { data: providers } = useQuery({
    queryKey: ['catalog-services'],
    queryFn: () =>
      api.get<{ id: number; name: string; color: string; note: string | null }[]>(
        '/api/services',
      ),
  })

  function toggle<T>(list: T[], value: T): T[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
  }

  async function finish() {
    setProblem(null)
    /* Seed the taste vector from the picks before saving the profile, so
       the first shelves are already personal. One failure here is not worth
       trapping someone in the dialog, so it is best effort. */
    for (const pick of liked) {
      try {
        await api.post(`/api/titles/${pick.type}/${pick.tmdb_id}/signal`, { kind: 'like' })
      } catch {
        // Carry on: a missing signal costs a little accuracy, nothing more.
      }
    }
    updateProfile.mutate(
      {
        country_code: country ?? undefined,
        services,
        languages,
        genres,
      },
      {
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
        // Without this the button simply re-enabled and nothing happened,
        // with no way out of a dialog that covers the whole screen.
        onError: (error) =>
          setProblem(
            error instanceof Error ? error.message : 'could not save that, try again',
          ),
      },
    )
  }

  /* Always a way out. A first run that can fail closed is worse than no
     first run at all. */
  function skip() {
    updateProfile.mutate(
      { country_code: country ?? 'US' },
      { onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }) },
    )
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') skip()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [country])

  const steps = [
    {
      title: 'Where do you watch from?',
      hint: 'Availability and release alerts follow your country.',
      valid: country !== null,
      body: (
        <div className="flex flex-wrap gap-2">
          {COUNTRIES.map((c) => (
            <Chip key={c.code} active={country === c.code} onClick={() => setCountry(c.code)}>
              {c.name}
            </Chip>
          ))}
        </div>
      ),
    },
    {
      title: 'Which services do you pay for?',
      hint: 'Suggestions and alerts prefer what you can actually press play on.',
      valid: true,
      body: providers ? (
        <div className="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-3">
          {providers.map((p) => (
            <button
              key={p.id}
              onClick={() => setServices(toggle(services, p.id))}
              className={clsx(
                'flex items-center gap-2 rounded-[4px] border px-3 py-2 text-left text-sm transition-colors',
                services.includes(p.id)
                  ? 'border-ember bg-ember/10'
                  : 'border-line hover:border-line/70',
              )}
            >
              <span
                aria-hidden
                className="h-5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: p.color }}
              />
              <span className="truncate">{p.name}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted">Loading services.</p>
      ),
    },
    {
      title: 'Which cinema cultures speak to you?',
      hint: 'Arabic, English, Korean: suggestions lean toward the languages you pick.',
      valid: true,
      body: (
        <div className="flex flex-wrap gap-2">
          {CULTURES.map((c) => (
            <Chip
              key={c.code}
              active={languages.includes(c.code)}
              onClick={() => setLanguages(toggle(languages, c.code))}
            >
              {c.name}
            </Chip>
          ))}
        </div>
      ),
    },
    {
      title: 'What do you usually reach for?',
      hint: 'A starting point only. The algorithm learns from every click after this.',
      valid: true,
      body: (
        <div className="flex flex-wrap gap-2">
          {GENRES.map((g) => (
            <Chip
              key={g.id}
              active={genres.includes(g.id)}
              onClick={() => setGenres(toggle(genres, g.id))}
            >
              {g.name}
            </Chip>
          ))}
        </div>
      ),
    },
  ]

  steps.push({
    title: 'Pick a few you like',
    hint: 'This is what the first suggestions are built from. Anything you pick counts as a like.',
    body: <TastePicker chosen={liked} onChange={setLiked} />,
    valid: liked.length >= TASTE_MINIMUM,
  })

  steps.push({
    title: 'Bring your history',
    hint: 'Optional, and you can do it any time from Settings.',
    body: (
      <div className="flex flex-col gap-2">
        <a
          href="https://www.netflix.com/account/getmyinfo"
          target="_blank"
          rel="noreferrer noopener"
          className="flex items-center justify-between rounded-[6px] border border-line bg-panel-2 px-4 py-3 transition-colors hover:border-ember"
        >
          <span className="text-sm">Netflix viewing history</span>
          <span className="font-mono text-[11px] text-ember">ready</span>
        </a>
        {['Letterboxd', 'Trakt', 'A browser extension'].map((name) => (
          <div
            key={name}
            className="flex items-center justify-between rounded-[6px] border border-dashed border-line px-4 py-3 opacity-60"
          >
            <span className="text-sm">{name}</span>
            <span className="font-mono text-[11px] text-muted">coming soon</span>
          </div>
        ))}
      </div>
    ),
    valid: true,
  })

  const current = steps[step]
  const isLast = step === steps.length - 1

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/90 px-6 backdrop-blur-sm">
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Set up your account"
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="wd-plate wd-scroller max-h-[90vh] w-full max-w-lg overflow-y-auto p-7"
      >
        <div className="flex items-center gap-2.5">
          <BeamMark className="h-6 w-6" />
          <p className="wd-eyebrow">
            Step {step + 1} of {steps.length}
          </p>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <h2 className="mt-4 font-display text-2xl font-semibold uppercase tracking-[0.02em]">
              {current.title}
            </h2>
            <p className="mt-1 text-sm text-muted">{current.hint}</p>
            <div className="mt-5">{current.body}</div>
          </motion.div>
        </AnimatePresence>

        {problem && (
          <p role="alert" className="mt-4 text-sm text-danger">
            {problem}
          </p>
        )}

        <div className="mt-7 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setStep(Math.max(0, step - 1))}
              disabled={step === 0}
              className="text-sm text-muted transition-colors hover:text-fg disabled:opacity-0"
            >
              Back
            </button>
            <button
              onClick={skip}
              className="text-sm text-muted transition-colors hover:text-fg"
            >
              Skip for now
            </button>
          </div>
          <button
            onClick={() => (isLast ? finish() : setStep(step + 1))}
            disabled={!current.valid || updateProfile.isPending}
            className="rounded-[4px] bg-ember px-6 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-40"
          >
            {isLast ? 'Start watching' : 'Next'}
          </button>
        </div>
      </motion.div>
    </div>
  )
}
