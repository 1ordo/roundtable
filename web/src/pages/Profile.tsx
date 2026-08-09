import { motion } from 'motion/react'
import { Link, useParams } from 'react-router'
import { img } from '../api/catalog'
import { nameOf, useProfile, useProfilePosts } from '../api/social2'
import { PostCard } from '../components/PostCard'
import { YearGrid } from '../components/YearGrid'
import { ScreenLoader } from '../components/ScreenLoader'

const HIDDEN_TEXT: Record<string, string> = {
  numbers: 'their numbers',
  favourites: 'their favourites',
  lists: 'their lists',
  posts: 'their posts',
  genres: 'what they watch',
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="wd-plate px-4 py-3">
      <p className="font-display text-2xl">{value}</p>
      <p className="mt-0.5 font-mono text-[10px] tracking-wider text-muted uppercase">{label}</p>
    </div>
  )
}

export function Profile() {
  const { handle = '' } = useParams()
  const { data, error, isLoading } = useProfile(handle)
  const { data: posts } = useProfilePosts(handle)

  if (isLoading) return <ScreenLoader />
  if (error || !data) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h1 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">No one by that name</h1>
        <p className="mt-2 text-sm text-muted">
          The handle may have changed, or the account may be gone.
        </p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-8">
        <p className="wd-eyebrow">Together</p>
        <div className="mt-3 flex flex-wrap items-center gap-4">
        {data.avatar_path ? (
          <img
            src={data.avatar_path}
            alt=""
            className="h-20 w-20 rounded-full border border-line object-cover"
          />
        ) : (
          <span className="flex h-20 w-20 items-center justify-center rounded-full bg-panel-2 font-display text-2xl text-ember">
            {nameOf(data as never).replace('@', '').slice(0, 1).toUpperCase()}
          </span>
        )}
        <div className="min-w-0">
          <h1 className="font-display text-4xl font-semibold uppercase tracking-[0.01em]">
            {data.display_name || data.handle || data.username}
          </h1>
          {data.handle && <p className="font-mono text-sm text-muted">@{data.handle}</p>}
          {data.joined && (
            <p className="mt-1 text-xs text-muted">
              Here since {new Date(data.joined).toLocaleDateString(undefined, {
                month: 'long',
                year: 'numeric',
              })}
            </p>
          )}
        </div>
        <div className="ml-auto">
          {data.yours ? (
            <Link
              to="/app/settings"
              className="rounded-[4px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
            >
              Edit profile
            </Link>
          ) : data.friend_status === 'accepted' ? (
            <div className="flex items-center gap-2">
              <Link
                to={`/app/messages/${data.handle}`}
                className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink hover:bg-ember/90"
              >
                Message
              </Link>
              <span className="rounded-[4px] border border-ember/50 px-4 py-2 text-sm text-ember">
                Friends
              </span>
            </div>
          ) : (
            <Link
              to="/app/friends"
              className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink hover:bg-ember/90"
            >
              {data.friend_status === 'pending' ? 'Request sent' : 'Add friend'}
            </Link>
          )}
        </div>
        </div>
      </header>

      {data.watched != null && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="watched" value={String(data.watched)} />
          <Stat label="hours" value={String(data.hours ?? 0)} />
          <Stat label="loved" value={String(data.loved ?? 0)} />
          {data.avg_rating != null && (
            <Stat label="average" value={String(data.avg_rating)} />
          )}
          {data.streak != null && <Stat label="day streak" value={String(data.streak)} />}
        </div>
      )}

      {/* The same grid they see on their own stats page, so a profile is a
          real page rather than three numbers. */}
      {data.days && data.days.length > 0 && (
        <YearGrid days={data.days} years={data.years ?? []} />
      )}

      {data.genres && data.genres.length > 0 && (
        <section className="mt-8">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">What they watch</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {data.genres.map((genre) => (
              <span
                key={genre.name}
                className="rounded-full border border-line px-3 py-1 text-xs text-muted"
              >
                {genre.name} <span className="font-mono text-ember">{genre.count}</span>
              </span>
            ))}
          </div>
        </section>
      )}

      {data.favourites && data.favourites.length > 0 && (
        <section className="mt-8">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Favourites</h2>
          <div className="mt-3 grid grid-cols-4 gap-3 sm:grid-cols-6">
            {data.favourites.map((title, i) => (
              <motion.div
                key={`${title.type}-${title.tmdb_id}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.03, 0.25) }}
              >
                <Link to={`/app/title/${title.type}/${title.tmdb_id}`} className="group block">
                  {title.poster_path ? (
                    <img
                      src={img(title.poster_path, 'w185') ?? ''}
                      alt={title.name}
                      loading="lazy"
                      className="aspect-[2/3] w-full rounded-lg border border-line object-cover transition-colors group-hover:border-ember"
                    />
                  ) : (
                    <span className="flex aspect-[2/3] w-full items-center justify-center rounded-lg bg-panel p-1 text-center text-[10px] text-muted">
                      {title.name}
                    </span>
                  )}
                </Link>
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {data.lists && data.lists.length > 0 && (
        <section className="mt-8">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Lists</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {data.lists.map((listing) => (
              <span
                key={listing.id}
                className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm"
              >
                {listing.name}{' '}
                <span className="font-mono text-xs text-muted">{listing.count}</span>
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Lines they kept, set against the poster of the film they are from
          and attributed to whoever says them. */}
      {data.quotes && data.quotes.length > 0 && (
        <section className="mt-8">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Lines they keep</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {data.quotes.map((quote, i) => (
              <motion.figure
                key={quote.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.05, 0.3) }}
                className="wd-plate relative flex gap-3 overflow-hidden p-3"
              >
                <Link
                  to={`/app/title/${quote.title.type}/${quote.title.tmdb_id}`}
                  className="shrink-0"
                >
                  {quote.title.poster_path ? (
                    <img
                      src={img(quote.title.poster_path, 'w185') ?? ''}
                      alt={quote.title.name}
                      loading="lazy"
                      className="h-24 w-16 rounded-lg object-cover transition-opacity hover:opacity-80"
                    />
                  ) : (
                    <span className="block h-24 w-16 rounded-lg bg-panel-2" />
                  )}
                </Link>
                <div className="flex min-w-0 flex-col justify-center">
                  <blockquote className="font-display leading-snug">
                    {quote.body}
                  </blockquote>
                  <figcaption className="mt-2 min-w-0">
                    {quote.character && (
                      <span className="block truncate font-mono text-[11px] text-ember">
                        {quote.character}
                      </span>
                    )}
                    <span className="block truncate text-[11px] text-muted">
                      {quote.title.name}
                      {quote.title.year ? ` (${quote.title.year})` : ''}
                    </span>
                  </figcaption>
                </div>
              </motion.figure>
            ))}
          </div>
        </section>
      )}

      {posts && !posts.hidden && posts.comments.length > 0 && (
        <section className="mt-8">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Posts</h2>
          <div className="mt-3 flex flex-col gap-4">
            {posts.comments.map((entry) => (
              <PostCard key={entry.id} post={entry} />
            ))}
          </div>
        </section>
      )}

      {/* Said plainly rather than left as a gap, so a hidden panel does not
          read as an empty one. */}
      {data.hidden.length > 0 && (
        <p className="mt-8 rounded-md border border-dashed border-line px-4 py-3 text-sm text-muted">
          {data.display_name || data.handle} keeps{' '}
          {data.hidden.map((h) => HIDDEN_TEXT[h] ?? h).join(', ')} to themselves.
        </p>
      )}
    </div>
  )
}
