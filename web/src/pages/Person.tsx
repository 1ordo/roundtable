import { motion } from 'motion/react'
import { Link, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { img } from '../api/catalog'
import { ScreenLoader } from '../components/ScreenLoader'
import { LoadError } from '../components/SetupNotice'
import { FollowButton } from '../components/PeopleResults'

type Credit = {
  tmdb_id: number
  type: 'movie' | 'tv'
  name: string
  poster_path: string | null
  year: number | null
  character: string | null
  job: string | null
}

type PersonOut = {
  id: number
  name: string
  biography: string | null
  birthday: string | null
  deathday: string | null
  place_of_birth: string | null
  profile_path: string | null
  known_for_department: string | null
  imdb_id: string | null
  acting: Credit[]
  crew: Credit[]
}

function age(birthday: string, deathday: string | null): number {
  const end = deathday ? new Date(deathday) : new Date()
  const born = new Date(birthday)
  let years = end.getFullYear() - born.getFullYear()
  const month = end.getMonth() - born.getMonth()
  if (month < 0 || (month === 0 && end.getDate() < born.getDate())) years -= 1
  return years
}

function CreditGrid({ credits, label }: { credits: Credit[]; label: string }) {
  if (credits.length === 0) return null
  return (
    <section className="mt-10 min-w-0">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">{label}</h2>
      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {credits.map((credit, i) => (
          <motion.div
            key={`${credit.type}-${credit.tmdb_id}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.4), duration: 0.35 }}
            className="min-w-0"
          >
            <Link to={`/app/title/${credit.type}/${credit.tmdb_id}`} className="group block">
              <img
                src={img(credit.poster_path, 'w342') ?? ''}
                alt={credit.name}
                loading="lazy"
                className="aspect-[2/3] w-full rounded-[6px] border border-line object-cover transition-colors group-hover:border-ember"
              />
              <p className="mt-2 truncate text-sm">{credit.name}</p>
              <p className="truncate font-mono text-[11px] text-muted">
                {credit.character || credit.job || ''}
                {credit.year ? ` ${credit.year}` : ''}
              </p>
            </Link>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

export function Person() {
  const { personId = '' } = useParams()
  const { data, error, isLoading } = useQuery({
    queryKey: ['person', personId],
    queryFn: () => api.get<PersonOut>(`/api/people/${personId}`),
    retry: false,
  })
  // The follow list is small and shared across pages, so reading it here
  // is cheaper than adding a per-person follow lookup to the detail call.
  const { data: following } = useQuery({
    queryKey: ['following'],
    queryFn: () => api.get<{ person_id: number }[]>('/api/following'),
    staleTime: 60_000,
  })
  const isFollowed = (following ?? []).some((p) => p.person_id === Number(personId))

  if (isLoading) return <ScreenLoader />
  if (error) return <LoadError />
  if (!data) return null

  const photo = img(data.profile_path, 'w500')

  return (
    <div className="min-w-0">
      <div className="flex flex-col gap-6 sm:flex-row sm:gap-8">
        {photo ? (
          <motion.img
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            src={photo}
            alt={data.name}
            className="w-36 shrink-0 self-start rounded-[6px] border border-line object-cover shadow-2xl shadow-black/50 sm:w-44"
          />
        ) : (
          <div className="flex h-44 w-36 shrink-0 items-center justify-center rounded-[6px] border border-line bg-panel-2 font-display text-4xl text-ember sm:w-44">
            {data.name.slice(0, 1)}
          </div>
        )}

        <div className="min-w-0 flex-1">
          <p className="wd-eyebrow">Explore</p>
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]"
          >
            {data.name}
          </motion.h1>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.15, duration: 0.4 }}
            className="mt-3"
          >
            <FollowButton personId={Number(personId)} following={isFollowed} />
            <p className="mt-1.5 text-xs text-muted">
              {isFollowed
                ? 'You get told when they have something new, and their work ranks higher for you.'
                : 'Follow to hear about their new work and see more of it in your suggestions.'}
            </p>
          </motion.div>

          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-muted">
            {data.known_for_department && <span>{data.known_for_department}</span>}
            {data.birthday && (
              <span>
                {data.deathday
                  ? `${data.birthday.slice(0, 4)} to ${data.deathday.slice(0, 4)}`
                  : `born ${data.birthday}, age ${age(data.birthday, null)}`}
              </span>
            )}
            {data.place_of_birth && <span>{data.place_of_birth}</span>}
          </p>

          {data.biography && (
            <p className="mt-5 max-w-2xl leading-relaxed whitespace-pre-line text-fg/90">
              {data.biography.length > 900
                ? `${data.biography.slice(0, 900).trimEnd()}...`
                : data.biography}
            </p>
          )}

          {data.imdb_id && (
            <a
              href={`https://www.imdb.com/name/${data.imdb_id}/`}
              target="_blank"
              rel="noreferrer"
              className="mt-5 inline-block rounded-[4px] border border-line bg-panel px-5 py-2.5 text-sm transition-colors hover:border-ember hover:text-ember"
            >
              View on IMDb
            </a>
          )}
        </div>
      </div>

      <CreditGrid credits={data.acting} label="Known for" />
      <CreditGrid credits={data.crew} label="Also worked on" />
    </div>
  )
}
