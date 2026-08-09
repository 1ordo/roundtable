import { useState } from 'react'
import { motion } from 'motion/react'
import { useTitleComments, useWriteComment, useWritePost } from '../api/social2'
import { PostCard } from './PostCard'

/* The conversation about one title, and the two ways to add to it: a
   comment, which lives on this page, and a post, which also goes to the
   feed. Same table underneath, so a comment is simply a post that names
   something. */
export function TitleComments({
  type,
  tmdbId,
  name,
}: {
  type: string
  tmdbId: number
  name: string
}) {
  const { data, isLoading } = useTitleComments(type, tmdbId)
  const comment = useWriteComment(type, tmdbId)
  const post = useWritePost()
  const [body, setBody] = useState('')
  const [spoiler, setSpoiler] = useState(false)

  function send(alsoPost: boolean) {
    const text = body.trim()
    if (!text) return
    const done = {
      onSuccess: () => {
        setBody('')
        setSpoiler(false)
      },
    }
    if (alsoPost) {
      post.mutate({ body: text, spoiler, type, tmdb_id: tmdbId }, done)
    } else {
      comment.mutate({ body: text, spoiler }, done)
    }
  }

  const busy = comment.isPending || post.isPending

  return (
    <section id="comments" className="mt-12 min-w-0 scroll-mt-20">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
        What people said
        {data && data.total > 0 && (
          <span className="ml-2 font-mono text-sm text-muted">{data.total}</span>
        )}
      </h2>

      <div className="wd-plate mt-4 p-4">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={`What did you make of ${name}?`}
          rows={2}
          className="w-full resize-none bg-transparent text-sm placeholder:text-muted focus:outline-none"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={spoiler}
              onChange={(e) => setSpoiler(e.target.checked)}
              className="accent-ember"
            />
            Contains a spoiler
          </label>
          <div className="flex gap-2">
            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={() => send(false)}
              disabled={!body.trim() || busy}
              className="rounded-[4px] border border-line px-3.5 py-1.5 text-sm text-muted transition-colors hover:border-ember hover:text-ember disabled:opacity-40"
            >
              Comment
            </motion.button>
            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={() => send(true)}
              disabled={!body.trim() || busy}
              title="Also shows in your friends' feed"
              className="rounded-[4px] bg-ember px-4 py-1.5 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-40"
            >
              {busy ? 'Posting' : 'Share'}
            </motion.button>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        {isLoading && <div className="h-24 animate-pulse rounded-md bg-panel" />}
        {data?.comments.map((entry) => (
          <PostCard key={entry.id} post={entry} compact />
        ))}
        {data && data.comments.length === 0 && !isLoading && (
          <p className="text-sm text-muted">
            Nothing yet. Whatever you write is seen by whoever can see your profile.
          </p>
        )}
      </div>
    </section>
  )
}
