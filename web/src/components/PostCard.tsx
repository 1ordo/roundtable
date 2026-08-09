import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Link } from 'react-router'
import clsx from 'clsx'
import { img } from '../api/catalog'
import {
  nameOf,
  profileHref,
  useDeletePost,
  useLikePost,
  useWritePost,
  type Post,
} from '../api/social2'

function when(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`
  return new Date(iso).toLocaleDateString()
}

export function Avatar({
  author,
  size = 'md',
}: {
  author: Post['author']
  size?: 'sm' | 'md'
}) {
  const box = size === 'sm' ? 'h-7 w-7 text-[10px]' : 'h-10 w-10 text-sm'
  const inner = author.avatar_path ? (
    <img
      src={author.avatar_path}
      alt=""
      className={`${box} shrink-0 rounded-full object-cover`}
    />
  ) : (
    <span
      className={`${box} flex shrink-0 items-center justify-center rounded-full bg-panel-2 text-ember`}
    >
      {nameOf(author).replace('@', '').slice(0, 1).toUpperCase()}
    </span>
  )
  const href = profileHref(author)
  return href ? <Link to={href}>{inner}</Link> : inner
}

/* Someone's name, clickable when they have picked a handle. Everywhere a
   person appears goes through this, so a person is never a dead end. */
export function PersonLink({
  author,
  className = '',
}: {
  author: Post['author']
  className?: string
}) {
  const href = profileHref(author)
  const label = nameOf(author)
  if (!href) return <span className={className}>{label}</span>
  return (
    <Link to={href} className={clsx('transition-colors hover:text-ember', className)}>
      {label}
    </Link>
  )
}

function TitleChip({ title }: { title: Post['title'] }) {
  if (!title) return null
  return (
    <Link
      to={`/app/title/${title.type}/${title.tmdb_id}`}
      className="mt-3 flex items-center gap-3 rounded-md border border-line bg-panel-2 p-2 transition-colors hover:border-ember"
    >
      {title.poster_path ? (
        <img
          src={img(title.poster_path, 'w185') ?? ''}
          alt=""
          loading="lazy"
          className="h-16 w-11 shrink-0 rounded object-cover"
        />
      ) : (
        <span className="h-16 w-11 shrink-0 rounded bg-panel" />
      )}
      <span className="min-w-0">
        <span className="block truncate text-sm">{title.name}</span>
        <span className="block font-mono text-[11px] text-muted">
          {title.type === 'tv' ? 'Series' : 'Film'} {title.year ?? ''}
        </span>
      </span>
    </Link>
  )
}

function Body({ post }: { post: Post }) {
  const [shown, setShown] = useState(!post.spoiler)
  if (!shown) {
    return (
      <button
        onClick={() => setShown(true)}
        className="mt-2 w-full rounded-[4px] border border-dashed border-line px-3 py-3 text-left text-sm text-muted transition-colors hover:border-ember hover:text-ember"
      >
        Spoiler. Tap to read.
      </button>
    )
  }
  return <p className="mt-2 leading-relaxed whitespace-pre-wrap">{post.body}</p>
}

export function PostCard({ post, compact = false }: { post: Post; compact?: boolean }) {
  const like = useLikePost()
  const remove = useDeletePost()
  const share = useWritePost()
  const [sharing, setSharing] = useState(false)
  const [replying, setReplying] = useState(false)
  const [reply, setReply] = useState('')
  const [thought, setThought] = useState('')
  const [confirming, setConfirming] = useState(false)

  function submitReply() {
    const text = reply.trim()
    if (!text) return
    share.mutate(
      { body: text, reply_to: post.id },
      {
        onSuccess: () => {
          setReplying(false)
          setReply('')
        },
      },
    )
  }

  function submitShare() {
    const text = thought.trim()
    if (!text) return
    share.mutate(
      { body: text, shares: post.shared?.id ?? post.id },
      {
        onSuccess: () => {
          setSharing(false)
          setThought('')
        },
      },
    )
  }

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'wd-plate min-w-0 p-4',
        compact && 'p-3',
      )}
    >
      <div className="flex items-center gap-3">
        <Avatar author={post.author} />
        <div className="min-w-0 flex-1">
          <PersonLink author={post.author} className="block truncate text-sm" />
          <p className="font-mono text-[11px] text-muted">
            {when(post.created_at)}
            {post.edited_at && ', edited'}
          </p>
        </div>
        {post.yours && (
          <button
            onClick={() => setConfirming(true)}
            aria-label="Delete this post"
            className="shrink-0 font-mono text-[11px] text-muted transition-colors hover:text-danger"
          >
            delete
          </button>
        )}
      </div>

      <Body post={post} />

      {/* A shared post keeps the original inside it, so the words on top are
          clearly yours and the words underneath are clearly not. */}
      {post.shared && (
        <div className="mt-3 rounded-md border border-line bg-panel-2 p-3">
          <div className="flex items-center gap-2">
            <Avatar author={post.shared.author} size="sm" />
            <PersonLink author={post.shared.author} className="truncate text-xs" />
            <span className="font-mono text-[10px] text-muted">
              {when(post.shared.created_at)}
            </span>
          </div>
          <p className="mt-1.5 text-sm whitespace-pre-wrap text-fg/85">{post.shared.body}</p>
          <TitleChip title={post.shared.title} />
        </div>
      )}

      {!post.shared && <TitleChip title={post.title} />}

      <div className="mt-3 flex items-center gap-1">
        <button
          onClick={() => like.mutate(post.id)}
          aria-pressed={post.you_liked}
          className={clsx(
            'flex items-center gap-1.5 rounded-[4px] px-2.5 py-1.5 text-xs transition-colors',
            post.you_liked ? 'text-ember' : 'text-muted hover:text-fg',
          )}
        >
          {/* Keyed on the state so the fill remounts and springs both
              ways: pressing and unpressing should both feel like an act. */}
          <motion.span
            key={post.you_liked ? 'on' : 'off'}
            initial={{ scale: 0.6 }}
            animate={{ scale: [0.6, 1.25, 1] }}
            transition={{ duration: 0.32, ease: 'easeOut' }}
            className="block"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-4 w-4"
              fill={post.you_liked ? 'currentColor' : 'none'}
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden
            >
              <path d="M12 20s-7-4.5-7-9.5A4 4 0 0 1 12 7a4 4 0 0 1 7 3.5c0 5-7 9.5-7 9.5Z" />
            </svg>
          </motion.span>
          {post.likes > 0 ? post.likes : 'like'}
        </button>

        {/* Replies are about what was said, not about the film, so this
            opens a box here rather than sending you to the title page. */}
        <button
          onClick={() => setReplying((open) => !open)}
          className={clsx(
            'rounded-[4px] px-2.5 py-1.5 text-xs transition-colors',
            replying ? 'text-ember' : 'text-muted hover:text-fg',
          )}
        >
          {post.reply_count > 0 ? `${post.reply_count} replies` : 'reply'}
        </button>

        <button
          onClick={() => setSharing((open) => !open)}
          className={clsx(
            'rounded-[4px] px-2.5 py-1.5 text-xs transition-colors',
            sharing ? 'text-ember' : 'text-muted hover:text-fg',
          )}
        >
          share
        </button>
      </div>

      {/* Replies, one level deep. A reply to a reply attaches to the same
          post, so a thread stays readable. */}
      {post.replies.length > 0 && (
        <div className="mt-3 flex flex-col gap-2 border-l border-line pl-3">
          {post.replies.map((entry) => (
            <div key={entry.id} className="flex items-start gap-2.5">
              <Avatar author={entry.author} size="sm" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <PersonLink author={entry.author} className="truncate text-xs" />
                  <span className="font-mono text-[10px] text-muted">
                    {when(entry.created_at)}
                  </span>
                  <button
                    onClick={() => like.mutate(entry.id)}
                    className={clsx(
                      'ml-auto shrink-0 font-mono text-[10px]',
                      entry.you_liked ? 'text-ember' : 'text-muted hover:text-fg',
                    )}
                  >
                    {entry.likes > 0 ? `${entry.likes} liked` : 'like'}
                  </button>
                </div>
                <p className="mt-0.5 text-sm whitespace-pre-wrap">{entry.body}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      <AnimatePresence>
        {replying && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-2 flex gap-2">
              <input
                value={reply}
                onChange={(event) => setReply(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && submitReply()}
                placeholder="Say something back"
                autoFocus
                className="min-w-0 flex-1 rounded-[4px] border border-line bg-panel-2 px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
              />
              <button
                onClick={submitReply}
                disabled={!reply.trim() || share.isPending}
                className="shrink-0 rounded-[4px] bg-ember px-3.5 py-2 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-40"
              >
                Reply
              </button>
            </div>
          </motion.div>
        )}

        {sharing && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-2 flex gap-2">
              <input
                value={thought}
                onChange={(e) => setThought(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submitShare()}
                placeholder="Say what you think of it"
                autoFocus
                className="min-w-0 flex-1 rounded-[4px] border border-line bg-panel-2 px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
              />
              <button
                onClick={submitShare}
                disabled={!thought.trim() || share.isPending}
                className="shrink-0 rounded-[4px] bg-ember px-3.5 py-2 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-40"
              >
                {share.isPending ? 'Sharing' : 'Share'}
              </button>
            </div>
          </motion.div>
        )}

        {confirming && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-danger/40 bg-danger/5 p-3">
              <span className="text-xs text-muted">
                Delete this? Anyone who shared it keeps their own words.
              </span>
              <button
                onClick={() => remove.mutate(post.id)}
                className="rounded-[4px] bg-danger px-3 py-1 text-xs font-medium text-ink"
              >
                Delete
              </button>
              <button
                onClick={() => setConfirming(false)}
                className="rounded-[4px] border border-line px-3 py-1 text-xs text-muted"
              >
                Keep
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  )
}
