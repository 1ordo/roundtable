import { motion } from 'motion/react'
import { Link, useParams } from 'react-router'
import { useSimilar, useVibeTags } from '../api/ai'
import { useSendSignal } from '../api/signals'
import { img, isNotConfigured, useTitle, type ProviderEntry } from '../api/catalog'
import { Row } from '../components/Row'
import { ScreenLoader } from '../components/ScreenLoader'
import { LoadError, SetupNotice } from '../components/SetupNotice'
import { TitleActions } from '../components/TitleActions'
import { Episodes } from '../components/Episodes'
import { ParentsGuide } from '../components/ParentsGuide'
import { TitleComments } from '../components/TitleComments'
import { Quotes } from '../components/Quotes'
import { Franchise } from '../components/Franchise'
import { ScoreChips } from '../components/ScoreChips'
import { CinemaTrack } from '../components/CinemaTrack'

function VibeTags({ type, tmdbId }: { type: string; tmdbId: number }) {
  const { data } = useVibeTags(type, tmdbId)
  if (!data || data.tags.length === 0) return null
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {data.tags.map((t) => (
        <span
          key={t.tag}
          title="Computed from the story itself, not from ratings"
          className="rounded-full px-3 py-1 text-xs"
          style={{
            border: '1px solid transparent',
            background:
              'linear-gradient(var(--color-panel), var(--color-panel)) padding-box, linear-gradient(90deg, var(--color-ember), var(--color-nitrate)) border-box',
          }}
        >
          {t.tag}
        </span>
      ))}
    </div>
  )
}

function SimilarRow({ type, tmdbId }: { type: string; tmdbId: number }) {
  const { data } = useSimilar(type, tmdbId)
  if (!data || data.results.length === 0) return null
  return (
    <section className="mt-10">
      <Row title="More like this" items={data.results} />
    </section>
  )
}

const KIND_LABEL: Record<ProviderEntry['kind'], string> = {
  stream: 'Stream',
  rent: 'Rent',
  buy: 'Buy',
  ads: 'Free with ads',
  free: 'Free',
}

export function TitleDetail() {
  const { type = '', tmdbId = '' } = useParams()
  const { data: title, error, isLoading } = useTitle(type, tmdbId)
  const sendSignal = useSendSignal(type, Number(tmdbId))

  if (isLoading) return <ScreenLoader />
  if (error) return isNotConfigured(error) ? <SetupNotice /> : <LoadError />
  if (!title) return null

  const backdrop = img(title.backdrop_path, 'w1280')
  const poster = img(title.poster_path, 'w500')
  // With no wide still, the poster itself becomes the atmosphere: blurred,
  // dimmed, and bled off the top of the page.
  const hero = backdrop ?? poster

  return (
    <div className="min-w-0">
      {hero && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7 }}
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[52vh] overflow-hidden"
        >
          <img
            src={hero}
            alt=""
            aria-hidden
            className="h-full w-full object-cover"
            style={{
              filter: backdrop ? 'none' : 'blur(48px) saturate(1.3)',
              transform: backdrop ? 'none' : 'scale(1.25)',
              opacity: backdrop ? 0.55 : 0.35,
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background:
                'linear-gradient(to top, var(--color-ink) 12%, transparent 88%), linear-gradient(to right, var(--color-ink) 2%, transparent 45%)',
            }}
          />
        </motion.div>
      )}

      <div>
        <div className="flex flex-col gap-8 md:flex-row">
          {poster && (
            <motion.img
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
              src={poster}
              alt={`${title.name} poster`}
              className="w-40 shrink-0 self-start rounded-[6px] border border-line shadow-2xl shadow-black/50 sm:w-48"
            />
          )}

          <div className="min-w-0 flex-1">
            <motion.h1
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="font-display text-5xl font-semibold uppercase tracking-[0.01em] md:text-6xl"
            >
              {title.name}
            </motion.h1>
            {title.original_name && title.original_name !== title.name && (
              <p className="mt-1 text-muted">{title.original_name}</p>
            )}

            <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-muted">
              <span className={title.type === 'movie' ? 'text-ember uppercase' : 'text-nitrate uppercase'}>
                {title.type === 'movie' ? 'Film' : 'Series'}
              </span>
              {title.year && <span>{title.year}</span>}
              {title.runtime && <span>{title.runtime} min</span>}
              {title.rated && title.rated !== 'N/A' && <span>{title.rated}</span>}
              {title.original_language && (
                <span className="uppercase">{title.original_language}</span>
              )}
              {title.match != null && (
                <span
                  className="rounded-full px-2 py-0.5 text-ember"
                  style={{
                    backgroundColor: 'color-mix(in srgb, var(--color-ember) 18%, transparent)',
                  }}
                  title="How well this fits you, learned from what you watch and rate"
                >
                  {title.match}% match
                </span>
              )}
            </p>

            {(title.director || title.country) && (
              <p className="mt-2 text-sm text-muted">
                {title.director && title.director !== 'N/A' && (
                  <span>
                    Directed by <span className="text-fg">{title.director}</span>
                  </span>
                )}
                {title.director && title.country && ' · '}
                {title.country && title.country !== 'N/A' && <span>{title.country}</span>}
              </p>
            )}

            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.15, duration: 0.5 }}
              className="mt-4"
            >
              <ScoreChips
                name={title.name}
                type={type}
                tmdbId={title.tmdb_id}
                imdbId={title.imdb_id}
                imdb={title.imdb_rating}
                rt={title.rt_score}
                metacritic={title.metacritic}
                tmdb={title.tmdb_rating}
              />
            </motion.div>

            {title.genres.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {title.genres.map((g) => (
                  <span
                    key={g.id}
                    className="rounded-full border border-ember/40 px-3 py-1 text-xs text-ember"
                  >
                    {g.name}
                  </span>
                ))}
              </div>
            )}

            <VibeTags type={title.type} tmdbId={title.tmdb_id} />

            {title.overview && (
              <p className="mt-5 max-w-2xl leading-relaxed text-fg/90">{title.overview}</p>
            )}

            {title.awards && title.awards !== 'N/A' && (
              <p className="mt-3 max-w-2xl text-sm text-muted">{title.awards}</p>
            )}

            {title.cast.length > 0 && (
              <p className="mt-3 max-w-2xl text-sm text-muted">
                With{' '}
                <span className="text-fg">
                  {title.cast
                    .slice(0, 4)
                    .map((c) => c.name)
                    .join(', ')}
                </span>
              </p>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              {title.trailer_youtube_key && (
                <a
                  href={`https://www.youtube.com/watch?v=${title.trailer_youtube_key}`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-[4px] border border-line bg-panel px-5 py-2.5 text-sm transition-colors hover:border-ember hover:text-ember"
                >
                  Watch trailer
                </a>
              )}
              {title.imdb_id && (
                <a
                  href={`https://www.imdb.com/title/${title.imdb_id}/`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-[4px] border border-line bg-panel px-5 py-2.5 text-sm transition-colors hover:border-ember hover:text-ember"
                >
                  View on IMDb
                </a>
              )}
            </div>

            <TitleActions type={title.type} tmdbId={title.tmdb_id} name={title.name} />
            {/* Only films, and only ones not already old: a cinema alert
                for something from 1994 would never fire. */}
            {title.type === 'movie' && (title.year ?? 0) >= new Date().getFullYear() - 1 && (
              <CinemaTrack tmdbId={title.tmdb_id} />
            )}
          </div>
        </div>

        <section className="mt-10">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Where to watch</h2>
          {Object.keys(title.availability).length === 0 ? (
            <p className="mt-3 text-sm text-muted">
              Not on any tracked service in {title.countries.join(', ')} right now. It lands in your
              notifications the day that changes.
            </p>
          ) : (
            <div className="mt-4 flex flex-col gap-5">
              {title.countries
                .filter((c) => title.availability[c]?.length)
                .map((country) => (
                  <div key={country}>
                    <p className="wd-eyebrow mb-2">{country}</p>
                    <div className="flex flex-wrap gap-2.5">
                      {title.availability[country].map((entry, i) => (
                        <a
                          key={`${entry.provider_name}-${entry.kind}-${i}`}
                          href={entry.url ?? undefined}
                          target="_blank"
                          rel="noreferrer"
                          onClick={() => sendSignal.mutate('click_out')}
                          className="wd-plate wd-plate--hover flex items-center gap-2.5 px-3.5 py-2"
                        >
                          {entry.logo_path && (
                            <img
                              src={img(entry.logo_path, 'w185') ?? ''}
                              alt=""
                              className="h-7 w-7 rounded"
                            />
                          )}
                          <span className="text-sm">{entry.provider_name}</span>
                          <span className="font-mono text-[10px] tracking-wider text-muted uppercase">
                            {KIND_LABEL[entry.kind]}
                          </span>
                        </a>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </section>

        {title.cast.length > 0 && (
          <section className="mt-10">
            <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Cast</h2>
            <div className="wd-scroller mt-4 flex gap-4 pb-3">
              {title.cast.map((member) => {
                const face = member.profile_path ? (
                  <img
                    src={img(member.profile_path, 'w185') ?? ''}
                    alt={member.name}
                    loading="lazy"
                    className="aspect-square w-24 rounded-full border border-line object-cover transition-colors group-hover/face:border-ember"
                  />
                ) : (
                  <div className="flex aspect-square w-24 items-center justify-center rounded-full border border-line bg-panel font-display text-xl text-muted transition-colors group-hover/face:border-ember">
                    {member.name.slice(0, 1)}
                  </div>
                )
                const body = (
                  <>
                    {face}
                    <p className="mt-2 truncate text-xs text-fg">{member.name}</p>
                    {member.character && (
                      <p className="truncate text-[11px] text-muted">{member.character}</p>
                    )}
                  </>
                )
                // Everyone with an id gets a page of their own work.
                return member.person_id ? (
                  <Link
                    key={`${member.person_id}-${member.name}`}
                    to={`/app/person/${member.person_id}`}
                    className="group/face w-24 shrink-0 text-center"
                  >
                    {body}
                  </Link>
                ) : (
                  <div key={member.name} className="w-24 shrink-0 text-center">
                    {body}
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* Above the guide and the comments: for a series this is the
            reason you opened the page. */}
        {title.type === 'tv' && <Episodes tmdbId={title.tmdb_id} />}

        <ParentsGuide
          certifications={title.certifications ?? {}}
          certification={title.certification}
          type={title.type}
          tmdbId={title.tmdb_id}
        />

        {title.collection_id && (
          <Franchise collectionId={title.collection_id} currentTmdbId={title.tmdb_id} />
        )}

        <Quotes type={title.type} tmdbId={title.tmdb_id} name={title.name} />

        <TitleComments type={title.type} tmdbId={title.tmdb_id} name={title.name} />

        <SimilarRow type={title.type} tmdbId={title.tmdb_id} />

        <div className="mt-10">
          <Link to="/app" className="text-sm text-muted transition-colors hover:text-fg">
            Back to home
          </Link>
        </div>
      </div>
    </div>
  )
}
