import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Link } from 'react-router'
import clsx from 'clsx'
import {
  useCreateNight,
  useFriends,
  useGiveVerdict,
  useMarkWatched,
  useNights,
  useQueueTitle,
  useRemovePick,
  useReplyToNight,
  useVotePick,
  type Night,
  type NightPick,
} from '../api/social'
import { img, useSearch } from '../api/catalog'
import { useMe } from '../app/useMe'
import { NightSuggest } from '../components/NightSuggest'

const STATUS_TEXT: Record<string, string> = {
  accepted: 'coming',
  invited: 'not answered',
  declined: 'cannot make it',
}

function Members({ night }: { night: Night }) {
  return (
    <div className="flex flex-wrap gap-2">
      {night.members.map((member) => (
        <span
          key={member.username}
          className={clsx(
            'flex items-center gap-2 rounded-full border py-1 pr-3 pl-1 text-xs',
            member.status === 'accepted'
              ? 'border-ember/50 text-fg'
              : member.status === 'declined'
                ? 'border-line text-muted line-through'
                : 'border-line text-muted',
          )}
        >
          {member.avatar_path ? (
            <img src={member.avatar_path} alt="" className="h-6 w-6 rounded-full object-cover" />
          ) : (
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-panel-2 text-[10px] text-ember">
              {member.username.slice(0, 1).toUpperCase()}
            </span>
          )}
          {member.username}
          <span className="text-muted">{STATUS_TEXT[member.status] ?? member.status}</span>
        </span>
      ))}
    </div>
  )
}

/* Add to the shared queue by searching. Both people use the same control,
   because the queue belongs to the night rather than to whoever made it. */
function AddToQueue({ night }: { night: Night }) {
  const [term, setTerm] = useState('')
  const { data } = useSearch(term)
  const queue = useQueueTitle()

  return (
    <div className="mt-4">
      <input
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="Suggest something"
        className="w-full rounded-[4px] border border-line bg-panel-2 px-3.5 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
      />
      {term.trim().length >= 2 && (
        <ul className="mt-2 flex flex-col gap-1">
          {(data?.results ?? []).slice(0, 5).map((result) => (
            <li key={`${result.type}-${result.tmdb_id}`}>
              <button
                onClick={() => {
                  queue.mutate({ id: night.id, type: result.type, tmdb_id: result.tmdb_id })
                  setTerm('')
                }}
                className="flex w-full items-center gap-3 rounded-[4px] px-2 py-1.5 text-left transition-colors hover:bg-panel-2"
              >
                {result.poster_path ? (
                  <img
                    src={img(result.poster_path, 'w185') ?? ''}
                    alt=""
                    className="h-12 w-8 shrink-0 rounded object-cover"
                  />
                ) : (
                  <span className="h-12 w-8 shrink-0 rounded bg-panel-2" />
                )}
                <span className="min-w-0">
                  <span className="block truncate text-sm">{result.name}</span>
                  <span className="block font-mono text-[11px] text-muted">
                    {result.type === 'tv' ? 'Series' : 'Film'} {result.year ?? ''}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function QueueRow({ night, pick }: { night: Night; pick: NightPick }) {
  const vote = useVotePick()
  const remove = useRemovePick()
  const settle = useMarkWatched()
  const { data: me } = useMe()
  const mine = pick.suggested_by === me?.user?.username
  const open = night.status === 'planning'

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="flex items-center gap-3 rounded-md border border-line bg-panel-2 p-2"
    >
      <Link to={`/app/title/${pick.type}/${pick.tmdb_id}`} className="shrink-0">
        {pick.poster_path ? (
          <img
            src={img(pick.poster_path, 'w185') ?? ''}
            alt={pick.name}
            className="h-16 w-11 rounded object-cover"
          />
        ) : (
          <span className="block h-16 w-11 rounded bg-panel" />
        )}
      </Link>

      <span className="min-w-0 flex-1">
        <Link
          to={`/app/title/${pick.type}/${pick.tmdb_id}`}
          className="block truncate text-sm hover:text-ember"
        >
          {pick.name}
        </Link>
        <span className="block font-mono text-[11px] text-muted">
          {pick.year ?? ''} {pick.suggested_by && `from ${pick.suggested_by}`}
        </span>
      </span>

      {open && (
        <motion.button
          whileTap={{ scale: 0.94 }}
          onClick={() => vote.mutate({ id: night.id, type: pick.type, tmdb_id: pick.tmdb_id })}
          aria-pressed={pick.you_voted}
          className={clsx(
            'flex shrink-0 items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 text-xs transition-colors',
            pick.you_voted
              ? 'border-ember bg-ember/15 text-ember'
              : 'border-line text-muted hover:text-fg',
          )}
        >
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
            <path d="M12 4l8 9h-5v7h-6v-7H4z" />
          </svg>
          {pick.votes}
        </motion.button>
      )}

      {open && night.you_host && (
        <button
          onClick={() => settle.mutate({ id: night.id, type: pick.type, tmdb_id: pick.tmdb_id })}
          className="shrink-0 rounded-[4px] bg-ember px-3 py-1.5 text-xs font-medium text-ink hover:bg-ember/90"
        >
          We watched this
        </button>
      )}

      {open && (mine || night.you_host) && (
        <button
          onClick={() => remove.mutate({ id: night.id, type: pick.type, tmdb_id: pick.tmdb_id })}
          aria-label={`Remove ${pick.name}`}
          className="shrink-0 rounded-[4px] border border-line px-2 py-1.5 text-xs text-muted transition-colors hover:border-danger hover:text-danger"
        >
          Remove
        </button>
      )}
    </motion.li>
  )
}

function Verdict({ night }: { night: Night }) {
  const give = useGiveVerdict()
  const [rating, setRating] = useState<number | null>(null)
  const [loved, setLoved] = useState(false)
  const [note, setNote] = useState('')

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 rounded-md border border-ember/40 bg-ember/5 p-4"
    >
      <p className="text-sm">So, what did you think of {night.watched?.name ?? 'it'}?</p>
      <div className="mt-3 flex flex-wrap gap-1">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
          <button
            key={n}
            onClick={() => setRating(n)}
            className={clsx(
              'h-8 w-8 rounded-[4px] border font-mono text-xs transition-colors',
              rating === n
                ? 'border-ember bg-ember text-ink'
                : 'border-line text-muted hover:text-fg',
            )}
          >
            {n}
          </button>
        ))}
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={loved}
          onChange={(e) => setLoved(e.target.checked)}
          className="accent-ember"
        />
        Loved it
      </label>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Anything you want to remember about it"
        rows={2}
        className="mt-3 w-full rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
      />
      <motion.button
        whileTap={{ scale: 0.97 }}
        disabled={give.isPending}
        onClick={() =>
          give.mutate({
            id: night.id,
            rating_10: rating,
            loved,
            note: note.trim() || null,
          })
        }
        className="mt-3 rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-50"
      >
        Save
      </motion.button>
      <p className="mt-2 text-xs text-muted">
        This rates it in your own history too, so your suggestions learn from it.
      </p>
    </motion.div>
  )
}

function NightCard({ night }: { night: Night }) {
  const reply = useReplyToNight()
  const takingPart = night.your_status === 'accepted'

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="wd-plate p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">{night.name}</h2>
        <span className="font-mono text-[11px] text-muted">
          {night.status === 'watched'
            ? `watched ${night.watched?.name ?? ''}`
            : `hosted by ${night.host}`}
        </span>
      </div>

      <div className="mt-3">
        <Members night={night} />
      </div>

      {night.your_status === 'invited' && (
        <div className="mt-4 flex gap-2">
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={() => reply.mutate({ id: night.id, coming: true })}
            className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink hover:bg-ember/90"
          >
            I am in
          </motion.button>
          <button
            onClick={() => reply.mutate({ id: night.id, coming: false })}
            className="rounded-[4px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:text-fg"
          >
            Cannot make it
          </button>
        </div>
      )}

      {night.your_status === 'declined' && (
        <p className="mt-4 text-sm text-muted">
          You said you cannot make this one.{' '}
          <button
            onClick={() => reply.mutate({ id: night.id, coming: true })}
            className="text-ember hover:underline"
          >
            Changed your mind?
          </button>
        </p>
      )}

      {takingPart && night.status === 'planning' && (
        <>
          <p className="wd-eyebrow mt-5">The queue</p>
          {night.queue.length === 0 ? (
            <p className="mt-2 text-sm text-muted">
              Empty. Ask for suggestions below, or search for something yourself.
            </p>
          ) : (
            <ul className="mt-2 flex flex-col gap-2">
              <AnimatePresence initial={false}>
                {night.queue.map((pick) => (
                  <QueueRow key={`${pick.type}-${pick.tmdb_id}`} night={night} pick={pick} />
                ))}
              </AnimatePresence>
            </ul>
          )}
          <AddToQueue night={night} />
          <NightSuggest night={night} />
        </>
      )}

      {night.status === 'watched' && night.watched && (
        <div className="mt-5 flex items-center gap-3">
          {night.watched.poster_path && (
            <Link to={`/app/title/${night.watched.type}/${night.watched.tmdb_id}`}>
              <img
                src={img(night.watched.poster_path, 'w185') ?? ''}
                alt={night.watched.name}
                className="h-20 w-14 rounded object-cover"
              />
            </Link>
          )}
          <span>
            <span className="block text-sm">{night.watched.name}</span>
            <span className="block text-xs text-muted">In the history of everyone who came.</span>
          </span>
        </div>
      )}

      {night.awaiting_your_verdict && <Verdict night={night} />}
    </motion.section>
  )
}

function NewNight() {
  const { data: friends } = useFriends()
  const create = useCreateNight()
  const [name, setName] = useState('')
  const [invite, setInvite] = useState<string[]>([])
  const [hours, setHours] = useState(12)

  const available = friends?.friends ?? []

  return (
    <section className="wd-plate p-5">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Plan one</h2>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="What are you calling it?"
        className="mt-3 w-full rounded-[4px] border border-line bg-panel-2 px-3.5 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
      />

      {available.length === 0 ? (
        <p className="mt-3 text-sm text-muted">
          You can plan one on your own, or{' '}
          <Link to="/app/friends" className="text-ember hover:underline">
            add a friend
          </Link>{' '}
          to invite someone.
        </p>
      ) : (
        <>
          <p className="wd-eyebrow mt-4">Invite</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {available.map((friend) => {
              const on = invite.includes(friend.username)
              return (
                <button
                  key={friend.id}
                  onClick={() =>
                    setInvite(
                      on
                        ? invite.filter((n) => n !== friend.username)
                        : [...invite, friend.username],
                    )
                  }
                  aria-pressed={on}
                  className={clsx(
                    'rounded-full border px-3 py-1.5 text-sm transition-colors',
                    on
                      ? 'border-ember bg-ember/15 text-ember'
                      : 'border-line text-muted hover:text-fg',
                  )}
                >
                  {friend.username}
                </button>
              )
            })}
          </div>
        </>
      )}

      <label className="mt-4 block text-xs text-muted">
        Ask everyone what they thought
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          className="mt-1 block rounded-[4px] border border-line bg-panel-2 px-3 py-1.5 text-sm text-fg focus:border-ember focus:outline-none"
        >
          <option value={0}>Straight away</option>
          <option value={3}>After 3 hours</option>
          <option value={12}>The next morning</option>
          <option value={24}>After a day</option>
          <option value={72}>After three days</option>
        </select>
      </label>

      <motion.button
        whileTap={{ scale: 0.97 }}
        disabled={!name.trim() || create.isPending}
        onClick={() =>
          create.mutate(
            { name: name.trim(), invite, survey_after_hours: hours },
            {
              onSuccess: () => {
                setName('')
                setInvite([])
              },
            },
          )
        }
        className="mt-4 rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-50"
      >
        Start it
      </motion.button>
      {create.isError && (
        <p className="mt-2 text-xs text-danger">
          {create.error instanceof Error ? create.error.message : 'Could not start that.'}
        </p>
      )}
    </section>
  )
}

export function WatchNight() {
  const { data: nights, isLoading } = useNights()

  return (
    <div className="max-w-3xl">
      <header className="mb-8">
        <p className="wd-eyebrow">Tonight</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Watch night
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Invite as many friends as you like. Everyone suggests, everyone votes, and whatever
          you settle on lands in all of your histories.
        </p>
      </header>

      <div className="flex flex-col gap-6">
        <NewNight />
        {isLoading && <div className="h-32 animate-pulse rounded-md bg-panel" />}
        <AnimatePresence initial={false}>
          {nights?.map((night) => <NightCard key={night.id} night={night} />)}
        </AnimatePresence>
      </div>
    </div>
  )
}
