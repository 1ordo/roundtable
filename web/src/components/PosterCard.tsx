import { Link } from 'react-router'
import clsx from 'clsx'
import { img, type TitleCard } from '../api/catalog'

/* Match is how well this fits the person looking at it, learned from
   everything they have watched, rated, liked, skipped and clicked. */
function MatchBadge({ value }: { value: number }) {
  const strong = value >= 70
  return (
    <span
      title={`${value}% match for you, learned from what you watch and rate`}
      className="rounded-full px-1.5 py-0.5 font-mono text-[10px] font-medium"
      style={{
        color: strong ? 'var(--color-ember)' : 'var(--color-muted)',
        backgroundColor: strong
          ? 'color-mix(in srgb, var(--color-ember) 18%, transparent)'
          : 'transparent',
      }}
    >
      {value}%
    </span>
  )
}

export function PosterCard({ title, index = 0 }: { title: TitleCard; index?: number }) {
  const poster = img(title.poster_path, 'w342')
  const rating = title.tmdb_rating

  return (
    // Plain div, animated by .wd-card in CSS. This is the most instantiated
    // component in the app, and as a motion component it put a JS tween and
    // a hover subscription on every one of the couple of hundred cards a
    // home page renders. See the .wd-card comment in index.css.
    <div
      className="wd-card w-36 shrink-0 sm:w-40"
      style={{ '--wd-delay': `${Math.min(index * 40, 500)}ms` } as React.CSSProperties}
    >
      <div className="wd-card__inner">
        <Link
          to={`/app/title/${title.type}/${title.tmdb_id}`}
          className="group/card relative block overflow-hidden rounded-[6px] border border-line bg-panel shadow-lg shadow-black/30 transition-colors hover:border-ember/60"
        >
          {poster ? (
            <img
              src={poster}
              alt={title.name}
              loading="lazy"
              className="aspect-[2/3] w-full object-cover"
            />
          ) : (
            <div className="flex aspect-[2/3] w-full items-center justify-center p-3 text-center font-display text-lg font-semibold text-muted uppercase">
              {title.name}
            </div>
          )}

          {rating != null && rating > 0 && (
            /* Decorative here: it repeats what the detail page states, and
             keeping it out of the accessible name leaves the link reading
             as just the title. */
            <span
              aria-hidden
              className="absolute top-1.5 left-1.5 rounded-[3px] bg-ink/85 px-1.5 py-0.5 font-mono text-[10px] text-fg backdrop-blur"
            >
              {rating.toFixed(1)}
            </span>
          )}

          {title.certification && (
            <span
              aria-hidden
              className="absolute top-1.5 right-1.5 rounded-[3px] bg-ink/85 px-1.5 py-0.5 font-mono text-[10px] text-fg backdrop-blur"
            >
              {title.certification}
            </span>
          )}

          {/* Which of the two things this is. Every shelf on the home page
            mixes them, and a poster alone does not say whether committing to
            it means two hours or six seasons. Bottom left, since the two top
            corners are already the rating and the age rating. The two-strip
            rule: films print in ember, series in nitrate. */}
          <span
            aria-hidden
            className={clsx(
              'absolute bottom-1.5 left-1.5 rounded-[3px] bg-ink/85 px-1.5 py-0.5 font-mono text-[10px] tracking-wider uppercase backdrop-blur',
              title.type === 'tv' ? 'text-nitrate' : 'text-ember',
            )}
          >
            {title.type === 'tv' ? 'Series' : 'Film'}
          </span>

          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ink/70 via-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover/card:opacity-100" />
        </Link>

        <div className="mt-2 flex items-baseline justify-between gap-2 px-0.5">
          <p className="truncate text-sm text-fg">{title.name}</p>
          <div className="flex shrink-0 items-baseline gap-1.5">
            {title.match != null && <MatchBadge value={title.match} />}
            {title.year && <span className="font-mono text-xs text-muted">{title.year}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
