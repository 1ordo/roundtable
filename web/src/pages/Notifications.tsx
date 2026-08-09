import { motion } from 'motion/react'
import { Link } from 'react-router'
import clsx from 'clsx'
import { img } from '../api/catalog'
import { useInbox, useMarkAllRead, useMarkRead, type NotificationOut } from '../api/notifications'

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function NotificationRow({ item, index }: { item: NotificationOut; index: number }) {
  const markRead = useMarkRead()
  /* The server decides where a row goes, because it is the side that knows
     what the row is about: a like goes to the person, a message to the
     conversation, anything about a title to the title. The old title-only
     rule sent a like about your post to the film instead of to whoever
     liked it. */
  const href =
    item.link ??
    (item.title_tmdb_id && item.title_type
      ? `/app/title/${item.title_type}/${item.title_tmdb_id}`
      : null)

  const body = (
    <div
      className={clsx(
        'flex items-center gap-4 rounded-md border p-3.5 transition-colors',
        item.read ? 'border-line bg-panel/50' : 'border-ember/40 bg-panel',
      )}
    >
      {item.title_poster ? (
        <img
          src={img(item.title_poster, 'w185') ?? ''}
          alt=""
          className="h-16 w-11 shrink-0 rounded-md object-cover"
        />
      ) : (
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-panel-2 text-muted">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M12 4a5.5 5.5 0 0 0-5.5 5.5c0 4-1.5 5.5-2.5 6.5h16c-1-1-2.5-2.5-2.5-6.5A5.5 5.5 0 0 0 12 4Zm-2.5 15a2.5 2.5 0 0 0 5 0" />
          </svg>
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className={clsx('text-sm', !item.read && 'text-fg', item.read && 'text-muted')}>
          {item.message}
        </p>
        <p className="mt-1 font-mono text-xs text-muted">{timeAgo(item.created_at)}</p>
      </div>
      {!item.read && <span className="wd-cue shrink-0 text-ember" />}
    </div>
  )

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.3), duration: 0.35 }}
    >
      {href ? (
        <Link to={href} onClick={() => !item.read && markRead.mutate(item.id)}>
          {body}
        </Link>
      ) : (
        <button
          className="w-full text-left"
          onClick={() => !item.read && markRead.mutate(item.id)}
        >
          {body}
        </button>
      )}
    </motion.div>
  )
}

export function Notifications() {
  const { data } = useInbox()
  const markAll = useMarkAllRead()

  return (
    <div className="max-w-2xl">
      <header className="mb-8">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="wd-eyebrow">The booth</p>
            <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
              Notifications
            </h1>
          </div>
          {data && data.unread > 0 && (
            <button
              onClick={() => markAll.mutate()}
              className="shrink-0 rounded-[4px] border border-line bg-panel px-4 py-2 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
            >
              Mark all read
            </button>
          )}
        </div>
        <p className="mt-2 max-w-xl text-sm text-muted">
          When a watchlist title lands on one of your services, it shows up here and pings
          your phone through ntfy.
        </p>
      </header>

      {data && data.notifications.length === 0 && (
        <p className="mt-10 text-muted">
          Nothing yet. Add titles to your watchlist and set your country and services in
          Settings.
        </p>
      )}

      <div className="mt-8 flex flex-col gap-2.5">
        {data?.notifications.map((item, i) => (
          <NotificationRow key={item.id} item={item} index={i} />
        ))}
      </div>
    </div>
  )
}
