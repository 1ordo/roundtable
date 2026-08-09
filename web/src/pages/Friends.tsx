import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import clsx from 'clsx'
import {
  useAcceptFriend,
  useAddFriend,
  useFriends,
  usePeopleSearch,
  useRemoveFriend,
  type Person,
} from '../api/social'
import { Link } from 'react-router'
import { useMe } from '../app/useMe'
import { useUpdateProfile } from '../api/tracking'

/* Everyone here is a link to their profile. A person you cannot open is a
   dead end, which is the whole complaint about a friends list that only
   lists names. Someone who never picked a handle has nowhere to go, so they
   stay plain rather than looking broken. */
function personHref(person: Person): string | null {
  return person.handle ? `/app/u/${person.handle}` : null
}

function personLabel(person: Person): string {
  return person.display_name || (person.handle ? `@${person.handle}` : person.username)
}

function Avatar({ person, size = 'md' }: { person: Person; size?: 'sm' | 'md' }) {
  const box = size === 'sm' ? 'h-9 w-9 text-sm' : 'h-11 w-11 text-base'
  const href = personHref(person)
  const inner = person.avatar_path ? (
    <img
      src={person.avatar_path}
      alt=""
      className={clsx(box, 'shrink-0 rounded-full border border-line object-cover')}
    />
  ) : (
    <div
      className={clsx(
        box,
        'flex shrink-0 items-center justify-center rounded-full bg-panel-2 font-display text-ember',
      )}
    >
      {personLabel(person).replace('@', '').slice(0, 1).toUpperCase()}
    </div>
  )
  return href ? (
    <Link to={href} className="shrink-0">
      {inner}
    </Link>
  ) : (
    inner
  )
}

function PersonRow({ person }: { person: Person }) {
  const add = useAddFriend()
  const accept = useAcceptFriend()
  const remove = useRemoveFriend()
  const busy = add.isPending || accept.isPending || remove.isPending

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="flex items-center gap-3 border-t border-line py-3 first:border-t-0"
    >
      <Avatar person={person} />
      <span className="min-w-0 flex-1">
        {personHref(person) ? (
          <Link
            to={personHref(person) as string}
            className="block truncate text-sm transition-colors hover:text-ember"
          >
            {personLabel(person)}
          </Link>
        ) : (
          <span className="block truncate text-sm">{personLabel(person)}</span>
        )}
        <span className="block text-xs text-muted">
          {person.relation === 'friends'
            ? 'Friends'
            : person.relation === 'pending_out'
              ? 'Asked'
              : person.relation === 'pending_in'
                ? 'Wants to be friends'
                : person.visibility === 'public'
                  ? 'Public profile'
                  : person.visibility === 'private'
                    ? 'Keeps to themselves'
                    : 'Friends only'}
        </span>
      </span>

      <span className="flex shrink-0 gap-2">
        {person.relation === 'none' && (
          <motion.button
            whileTap={{ scale: 0.96 }}
            disabled={busy}
            onClick={() => add.mutate(person.username)}
            className="rounded-[4px] bg-ember px-3 py-1.5 text-xs font-medium text-ink hover:bg-ember/90 disabled:opacity-50"
          >
            Add
          </motion.button>
        )}
        {person.relation === 'pending_in' && (
          <motion.button
            whileTap={{ scale: 0.96 }}
            disabled={busy}
            onClick={() => accept.mutate(person.username)}
            className="rounded-[4px] bg-ember px-3 py-1.5 text-xs font-medium text-ink hover:bg-ember/90 disabled:opacity-50"
          >
            Accept
          </motion.button>
        )}
        {person.relation === 'friends' && person.handle && (
          <Link
            to={`/app/messages/${person.handle}`}
            className="shrink-0 rounded-[4px] border border-line px-3 py-1.5 text-xs text-muted transition-colors hover:border-ember hover:text-ember"
          >
            Message
          </Link>
        )}
        {person.relation !== 'none' && (
          <button
            disabled={busy}
            onClick={() => remove.mutate(person.username)}
            className="rounded-[4px] border border-line px-3 py-1.5 text-xs text-muted transition-colors hover:border-danger hover:text-danger disabled:opacity-50"
          >
            {person.relation === 'friends'
              ? 'Remove'
              : person.relation === 'pending_out'
                ? 'Cancel'
                : 'Decline'}
          </button>
        )}
      </span>
    </motion.li>
  )
}

function Find() {
  const [text, setText] = useState('')
  const [term, setTerm] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const { data, isFetching } = usePeopleSearch(term)

  /* Debounced through a ref rather than a dependency, because a setter's
     identity changes every render and would reset the timer forever. */
  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setTerm(text), 300)
    return () => clearTimeout(timer.current)
  }, [text])

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Find someone</h2>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Search by name"
        className="mt-3 w-full rounded-[4px] border border-line bg-panel px-4 py-2.5 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
      />
      {term.length >= 2 && (
        <ul className="mt-2">
          <AnimatePresence initial={false}>
            {(data ?? []).map((person) => (
              <PersonRow key={person.id} person={person} />
            ))}
          </AnimatePresence>
          {!isFetching && data?.length === 0 && (
            <li className="py-4 text-sm text-muted">Nobody here by that name.</li>
          )}
        </ul>
      )}
    </section>
  )
}

export function Friends() {
  const { data } = useFriends()
  const { data: me } = useMe()
  const update = useUpdateProfile()
  const level = (me?.user?.visibility as string) ?? 'friends'

  return (
    <div className="max-w-2xl">
      <header className="mb-8">
        <p className="wd-eyebrow">Together</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Friends
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Nobody sees your history unless you are friends, or you make your profile public.
        </p>
      </header>

      {/* Three levels now, not a toggle, and each part of a profile can
          differ. The full set lives in Settings; this is the headline. */}
      <div className="wd-plate flex flex-wrap items-center justify-between gap-4 px-4 py-3.5">
        <span className="min-w-0">
          <span className="block text-sm">Who can see your things</span>
          <span className="mt-0.5 block text-xs text-muted">
            {level === 'public'
              ? 'Anyone signed in here can see your stats and lists.'
              : level === 'private'
                ? 'Nobody but you, not even friends.'
                : 'Friends only.'}{' '}
            <Link to="/app/settings" className="text-ember hover:underline">
              Set it per section
            </Link>
          </span>
        </span>
        <div className="flex rounded-md border border-line bg-panel-2 p-1">
          {[
            { key: 'public', label: 'Everyone' },
            { key: 'friends', label: 'Friends' },
            { key: 'private', label: 'Only me' },
          ].map((option) => (
            <button
              key={option.key}
              onClick={() => update.mutate({ visibility: option.key })}
              className={clsx(
                'rounded-[4px] px-3 py-1 text-xs transition-colors',
                level === option.key ? 'bg-ember text-ink' : 'text-muted hover:text-fg',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {(data?.incoming.length ?? 0) > 0 && (
        <section className="mt-10">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Wants to be friends</h2>
          <ul className="mt-3">
            <AnimatePresence initial={false}>
              {data?.incoming.map((person) => <PersonRow key={person.id} person={person} />)}
            </AnimatePresence>
          </ul>
        </section>
      )}

      <section className="mt-10">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Your friends</h2>
        {data?.friends.length === 0 ? (
          <p className="mt-3 text-sm text-muted">
            None yet. Search below to send the first request.
          </p>
        ) : (
          <ul className="mt-3">
            <AnimatePresence initial={false}>
              {data?.friends.map((person) => <PersonRow key={person.id} person={person} />)}
            </AnimatePresence>
          </ul>
        )}
      </section>

      {(data?.outgoing.length ?? 0) > 0 && (
        <section className="mt-10">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Waiting on them</h2>
          <ul className="mt-3">
            <AnimatePresence initial={false}>
              {data?.outgoing.map((person) => <PersonRow key={person.id} person={person} />)}
            </AnimatePresence>
          </ul>
        </section>
      )}

      <Find />
    </div>
  )
}
