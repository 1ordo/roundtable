import { motion } from 'motion/react'
import { Link } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { img } from '../api/catalog'

export type PersonResult = {
  person_id: number
  name: string
  profile_path: string | null
  known_for: string
  you_follow: boolean
}

export function useFollowPerson() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, following }: { id: number; following: boolean }) =>
      following
        ? api.delete(`/api/people/${id}/follow`)
        : api.post(`/api/people/${id}/follow`, {}),
    onSuccess: () => {
      // Search rows carry the follow state, and home ranks by it.
      queryClient.invalidateQueries({ queryKey: ['search'] })
      queryClient.invalidateQueries({ queryKey: ['following'] })
      queryClient.invalidateQueries({ queryKey: ['home'] })
    },
  })
}

export function FollowButton({
  personId,
  following,
  size = 'md',
}: {
  personId: number
  following: boolean
  size?: 'sm' | 'md'
}) {
  const follow = useFollowPerson()
  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      disabled={follow.isPending}
      onClick={(event) => {
        // Follow buttons sit inside links to the person page.
        event.preventDefault()
        event.stopPropagation()
        follow.mutate({ id: personId, following })
      }}
      aria-pressed={following}
      className={clsx(
        'shrink-0 rounded-[4px] border transition-colors disabled:opacity-50',
        size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-1.5 text-sm',
        following
          ? 'border-ember bg-ember/15 text-ember'
          : 'border-line text-muted hover:border-ember hover:text-ember',
      )}
    >
      {following ? 'Following' : 'Follow'}
    </motion.button>
  )
}

export function PeopleResults({ people }: { people: PersonResult[] }) {
  if (people.length === 0) return null
  return (
    <section className="mt-8 min-w-0">
      <h2 className="wd-eyebrow">People</h2>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {people.map((person, i) => (
          <motion.div
            key={person.person_id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.04, 0.3), duration: 0.3 }}
            className="min-w-0"
          >
            <Link
              to={`/app/person/${person.person_id}`}
              className="wd-plate wd-plate--hover flex items-center gap-3 p-2.5"
            >
              {person.profile_path ? (
                <img
                  src={img(person.profile_path, 'w185') ?? ''}
                  alt=""
                  loading="lazy"
                  className="h-12 w-12 shrink-0 rounded-full object-cover"
                />
              ) : (
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-panel-2 font-display text-lg text-muted">
                  {person.name.slice(0, 1)}
                </span>
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{person.name}</span>
                {person.known_for && (
                  <span className="block truncate text-xs text-muted">{person.known_for}</span>
                )}
              </span>
              <FollowButton
                personId={person.person_id}
                following={person.you_follow}
                size="sm"
              />
            </Link>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
