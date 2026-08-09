import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Link, useParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { img } from '../api/catalog'
import { nameOf, type PostAuthor } from '../api/social2'

type Message = {
  id: string
  body: string
  created_at: string
  mine: boolean
  read: boolean
  title: { tmdb_id: number; type: string; name: string; poster_path: string | null } | null
}

type Conversation = {
  person: PostAuthor
  last: string
  last_at: string
  unread: number
  from_them: boolean
}

function when(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`
  return new Date(iso).toLocaleDateString()
}

function Face({ person, size = 40 }: { person: PostAuthor; size?: number }) {
  const style = { width: size, height: size }
  return person.avatar_path ? (
    <img
      src={person.avatar_path}
      alt=""
      style={style}
      className="shrink-0 rounded-full object-cover"
    />
  ) : (
    <span
      style={style}
      className="flex shrink-0 items-center justify-center rounded-full bg-panel-2 text-sm text-ember"
    >
      {nameOf(person).replace('@', '').slice(0, 1).toUpperCase()}
    </span>
  )
}

function Thread({ handle }: { handle: string }) {
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['thread', handle],
    queryFn: () =>
      api.get<{ person: PostAuthor; messages: Message[] }>(`/api/messages/${handle}`),
    // Polling rather than sockets: a household does not need a live
    // connection held open, and this keeps the whole thing one request.
    refetchInterval: 15_000,
  })

  const send = useMutation({
    mutationFn: (text: string) => api.post(`/api/messages/${handle}`, { body: text }),
    onSuccess: () => {
      setBody('')
      queryClient.invalidateQueries({ queryKey: ['thread', handle] })
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      queryClient.invalidateQueries({ queryKey: ['messages-unread'] })
    },
  })

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [data?.messages.length])

  useEffect(() => {
    // Opening the thread marks it read, so the badge should follow.
    queryClient.invalidateQueries({ queryKey: ['messages-unread'] })
    queryClient.invalidateQueries({ queryKey: ['conversations'] })
  }, [handle, queryClient])

  return (
    <div className="flex min-h-[60vh] flex-col">
      {data?.person && (
        <Link
          to={`/app/u/${data.person.handle}`}
          className="flex items-center gap-3 border-b border-line pb-4 transition-colors hover:text-ember"
        >
          <Face person={data.person} />
          <span className="min-w-0">
            <span className="block truncate">{nameOf(data.person)}</span>
            <span className="block font-mono text-[11px] text-muted">see their profile</span>
          </span>
        </Link>
      )}

      <div className="flex flex-1 flex-col gap-2 py-4">
        {isLoading && <div className="h-20 animate-pulse rounded-md bg-panel" />}
        <AnimatePresence initial={false}>
          {data?.messages.map((message) => (
            <motion.div
              key={message.id}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={clsx('flex', message.mine ? 'justify-end' : 'justify-start')}
            >
              <div
                className={clsx(
                  'max-w-[80%] rounded-2xl px-4 py-2.5',
                  message.mine
                    ? 'rounded-br-sm bg-ember text-ink'
                    : 'rounded-bl-sm border border-line bg-panel',
                )}
              >
                <p className="text-sm whitespace-pre-wrap">{message.body}</p>
                {message.title && (
                  <Link
                    to={`/app/title/${message.title.type}/${message.title.tmdb_id}`}
                    className={clsx(
                      'mt-2 flex items-center gap-2 rounded-lg p-1.5 transition-colors',
                      message.mine ? 'bg-ink/10 hover:bg-ink/20' : 'bg-panel-2 hover:bg-line',
                    )}
                  >
                    {message.title.poster_path && (
                      <img
                        src={img(message.title.poster_path, 'w185') ?? ''}
                        alt=""
                        className="h-12 w-8 shrink-0 rounded object-cover"
                      />
                    )}
                    <span className="min-w-0 truncate text-xs">{message.title.name}</span>
                  </Link>
                )}
                <p
                  className={clsx(
                    'mt-1 font-mono text-[10px]',
                    message.mine ? 'text-ink/60' : 'text-muted',
                  )}
                >
                  {when(message.created_at)}
                </p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {data && data.messages.length === 0 && (
          <p className="py-8 text-center text-sm text-muted">
            Nothing here yet. Say hello.
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (body.trim()) send.mutate(body.trim())
        }}
        className="sticky bottom-0 flex gap-2 bg-ink py-4"
      >
        <input
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="Write something"
          className="min-w-0 flex-1 rounded-[4px] border border-line bg-panel px-4 py-3 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
        />
        <motion.button
          type="submit"
          whileTap={{ scale: 0.97 }}
          disabled={!body.trim() || send.isPending}
          className="rounded-[4px] bg-ember px-5 py-3 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-40"
        >
          Send
        </motion.button>
      </form>
    </div>
  )
}

export function Messages() {
  const { handle } = useParams()
  const { data, isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => api.get<Conversation[]>('/api/messages'),
    refetchInterval: 30_000,
  })

  if (handle) {
    return (
      <div className="mx-auto max-w-2xl">
        <Link
          to="/app/messages"
          className="font-mono text-[11px] text-muted transition-colors hover:text-fg"
        >
          all messages
        </Link>
        <div className="mt-3">
          <Thread handle={handle} />
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-8">
        <p className="wd-eyebrow">Together</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Messages
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Between friends only. Add someone as a friend first and you can write to each other.
        </p>
      </header>

      <div className="flex flex-col gap-2">
        {isLoading && <div className="h-16 animate-pulse rounded-md bg-panel" />}
        {data?.map((conversation) => (
          <Link
            key={conversation.person.handle ?? conversation.person.username}
            to={`/app/messages/${conversation.person.handle}`}
            className="wd-plate wd-plate--hover flex items-center gap-3 p-3"
          >
            <Face person={conversation.person} />
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-2">
                <span className="truncate text-sm">{nameOf(conversation.person)}</span>
                <span className="ml-auto shrink-0 font-mono text-[10px] text-muted">
                  {when(conversation.last_at)}
                </span>
              </span>
              <span
                className={clsx(
                  'mt-0.5 block truncate text-xs',
                  conversation.unread > 0 ? 'text-fg' : 'text-muted',
                )}
              >
                {conversation.from_them ? '' : 'You: '}
                {conversation.last}
              </span>
            </span>
            {conversation.unread > 0 && (
              <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-ember px-1.5 font-mono text-[10px] font-bold text-ink">
                {conversation.unread}
              </span>
            )}
          </Link>
        ))}
        {data && data.length === 0 && (
          <div className="rounded-md border border-dashed border-line p-8 text-center">
            <p className="text-sm text-muted">
              No messages yet. Open a{' '}
              <Link to="/app/friends" className="text-ember hover:underline">
                friend
              </Link>{' '}
              and write to them.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
