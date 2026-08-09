import { useState } from 'react'
import { motion } from 'motion/react'
import { Link } from 'react-router'
import { useFeed, useWritePost } from '../api/social2'
import { useMe } from '../app/useMe'
import { Avatar, PostCard } from '../components/PostCard'

export function Feed() {
  const { data, isLoading } = useFeed()
  const { data: me } = useMe()
  const write = useWritePost()
  const [body, setBody] = useState('')
  const [spoiler, setSpoiler] = useState(false)

  const author = {
    handle: me?.user?.handle ?? null,
    display_name: me?.user?.display_name ?? null,
    username: me?.user?.username ?? '',
    avatar_path: me?.user?.avatar_path ?? null,
  }

  function post() {
    const text = body.trim()
    if (!text) return
    write.mutate(
      { body: text, spoiler },
      {
        onSuccess: () => {
          setBody('')
          setSpoiler(false)
        },
      },
    )
  }

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-8">
        <p className="wd-eyebrow">Together</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Feed
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          What the people you follow have been watching and saying.
        </p>
      </header>

      <div className="wd-plate p-4">
        <div className="flex gap-3">
          <Avatar author={author} />
          <div className="min-w-0 flex-1">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="What did you watch?"
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
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={post}
                disabled={!body.trim() || write.isPending}
                className="rounded-[4px] bg-ember px-4 py-1.5 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-40"
              >
                {write.isPending ? 'Posting' : 'Post'}
              </motion.button>
            </div>
            <p className="mt-1 text-[11px] text-muted">
              Seen by whoever can see your profile. Attach a film by posting from its page.
            </p>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-4">
        {isLoading &&
          [...Array(3)].map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-md bg-panel" />
          ))}

        {data?.comments.map((entry) => <PostCard key={entry.id} post={entry} />)}

        {data && data.comments.length === 0 && (
          <div className="rounded-md border border-dashed border-line p-8 text-center">
            <p className="text-sm text-muted">
              Nothing here yet. Post something above, or{' '}
              <Link to="/app/friends" className="text-ember hover:underline">
                add a friend
              </Link>{' '}
              to see what they are watching.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
