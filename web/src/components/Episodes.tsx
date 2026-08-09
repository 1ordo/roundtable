import { useState } from 'react'
import clsx from 'clsx'
import { useEpisodes, useMarkEpisode, useMarkSeason } from '../api/episodes'
import type { EpisodeOut } from '../api/episodes'

function airLabel(episode: EpisodeOut): string {
  if (!episode.air_date) return 'No date yet'
  const when = new Date(episode.air_date)
  const text = when.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
  return episode.aired ? text : `Airs ${text}`
}

/** One episode row: a checkbox, its number, its name, and when it aired. */
function Row({
  episode,
  onToggle,
  busy,
}: {
  episode: EpisodeOut
  onToggle: (episode: EpisodeOut) => void
  busy: boolean
}) {
  // An episode that has not aired cannot be watched. The server refuses it
  // too; disabling here means the interface never offers something that
  // will fail.
  const locked = !episode.aired
  return (
    <li
      className={clsx(
        'flex items-center gap-3 border-b border-line/60 py-2 last:border-b-0',
        locked && 'opacity-55'
      )}
    >
      <input
        type="checkbox"
        checked={episode.watched}
        disabled={locked || busy}
        onChange={() => onToggle(episode)}
        aria-label={`Episode ${episode.episode}${episode.name ? `, ${episode.name}` : ''}${
          locked ? ', not out yet' : ''
        }`}
        className="size-4 shrink-0 accent-[var(--ember)] disabled:cursor-not-allowed"
      />
      <span className="w-10 shrink-0 font-mono text-xs text-muted">
        E{String(episode.episode).padStart(2, '0')}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm">{episode.name || 'Untitled'}</span>
      <span className="shrink-0 font-mono text-xs text-muted">{airLabel(episode)}</span>
    </li>
  )
}

export function Episodes({ tmdbId }: { tmdbId: number }) {
  const { data, isLoading, isError } = useEpisodes(tmdbId)
  const markEpisode = useMarkEpisode(tmdbId)
  const markSeason = useMarkSeason(tmdbId)
  const [open, setOpen] = useState<number | null>(null)

  if (isLoading) {
    return <p className="text-sm text-muted">Loading episodes…</p>
  }
  if (isError || !data || data.seasons.length === 0) {
    // A film, a show TMDB has no season data for, or the catalog is not
    // configured. Saying nothing beats an empty grid that looks broken.
    return null
  }

  const busy = markEpisode.isPending || markSeason.isPending
  // Default the open season to wherever they actually are.
  const current = open ?? data.next_up?.season ?? data.seasons[0].season

  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="wd-eyebrow wd-eyebrow--nitrate">Episodes</p>
        <p className="font-mono text-xs text-muted">
          {data.watched} of {data.aired} aired
          {data.upcoming > 0 ? `, ${data.upcoming} to come` : ''}
        </p>
      </div>

      {data.next_up ? (
        <div className="wd-plate mt-3 flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="min-w-0">
            <p className="wd-eyebrow wd-eyebrow--ember">Next up</p>
            <p className="mt-1 truncate text-sm">
              <span className="font-mono text-muted">
                S{data.next_up.season}E{data.next_up.episode}
              </span>{' '}
              {data.next_up.name || 'Untitled'}
            </p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              markEpisode.mutate({
                season: data.next_up!.season,
                episode: data.next_up!.episode,
                watched: true,
              })
            }
            className="rounded-[4px] border border-ember/50 px-3 py-1.5 text-xs text-ember transition-colors hover:bg-ember/10 disabled:opacity-50"
          >
            Mark watched
          </button>
        </div>
      ) : data.complete ? (
        <p className="mt-3 text-sm text-muted">
          You are up to date{data.upcoming > 0 ? '. More is on the way.' : '.'}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {data.seasons.map((season) => (
          <button
            key={season.season}
            type="button"
            onClick={() => setOpen(season.season)}
            aria-current={season.season === current}
            className={clsx(
              'rounded-[4px] border px-3 py-1.5 text-xs transition-colors',
              season.season === current
                ? 'border-ember text-ember'
                : 'border-line text-muted hover:border-ember hover:text-ember'
            )}
          >
            {season.season === 0 ? 'Specials' : `Season ${season.season}`}
          </button>
        ))}
      </div>

      {data.seasons
        .filter((season) => season.season === current)
        .map((season) => {
          const aired = season.episodes.filter((e) => e.aired)
          const allSeen = aired.length > 0 && aired.every((e) => e.watched)
          return (
            <div key={season.season} className="wd-plate mt-3 p-4">
              <div className="flex items-center justify-between gap-3 pb-2">
                <p className="font-mono text-xs text-muted">
                  {aired.filter((e) => e.watched).length} of {aired.length} watched
                </p>
                {aired.length > 0 ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      markSeason.mutate({ season: season.season, watched: !allSeen })
                    }
                    className="rounded-[4px] border border-line px-3 py-1.5 text-xs text-muted transition-colors hover:border-ember hover:text-ember disabled:opacity-50"
                  >
                    {allSeen ? 'Clear season' : 'Mark season watched'}
                  </button>
                ) : null}
              </div>
              <ul>
                {season.episodes.map((episode) => (
                  <Row
                    key={episode.id}
                    episode={episode}
                    busy={busy}
                    onToggle={(e) =>
                      markEpisode.mutate({
                        season: e.season,
                        episode: e.episode,
                        watched: !e.watched,
                      })
                    }
                  />
                ))}
              </ul>
            </div>
          )
        })}
    </section>
  )
}
