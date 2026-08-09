import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ApiError, api } from '../api/client'

type Quote = {
  id: string
  body: string
  character: string | null
  source: string
  added_by: string | null
  likes: number
  you_liked: boolean
  yours: boolean
}

type Suggestion = { text: string; character: string | null }

/* A line, set like a pull quote rather than a list item. The mark is drawn
   rather than typed so it sits where it should regardless of the font. */
function QuoteCard({
  quote,
  onLike,
  onDelete,
}: {
  quote: Quote
  onLike: () => void
  onDelete: () => void
}) {
  return (
    <motion.figure
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      className="wd-plate relative overflow-hidden p-5"
    >
      <svg
        viewBox="0 0 24 24"
        aria-hidden
        className="absolute top-3 left-3 h-8 w-8 text-ember/15"
        fill="currentColor"
      >
        <path d="M9 7H5a2 2 0 0 0-2 2v4h4v4H3v-6m18-4h-4a2 2 0 0 0-2 2v4h4v4h-4v-6" />
      </svg>
      <blockquote className="relative pl-6 font-display text-lg leading-snug">
        {quote.body}
      </blockquote>
      <figcaption className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 pl-6">
        {quote.character && (
          <span className="font-mono text-xs tracking-wide text-ember">
            {quote.character}
          </span>
        )}
        {quote.added_by && (
          <span className="text-[11px] text-muted">added by {quote.added_by}</span>
        )}
        <span className="ml-auto flex items-center gap-1">
          <button
            onClick={onLike}
            aria-pressed={quote.you_liked}
            className={clsx(
              'flex items-center gap-1.5 rounded-[4px] px-2 py-1 text-xs transition-colors',
              quote.you_liked ? 'text-ember' : 'text-muted hover:text-fg',
            )}
          >
            <svg
              viewBox="0 0 24 24"
              className="h-3.5 w-3.5"
              fill={quote.you_liked ? 'currentColor' : 'none'}
              stroke="currentColor"
              strokeWidth="1.8"
              aria-hidden
            >
              <path d="M12 20s-7-4.5-7-9.5A4 4 0 0 1 12 7a4 4 0 0 1 7 3.5c0 5-7 9.5-7 9.5Z" />
            </svg>
            {quote.likes > 0 ? quote.likes : ''}
          </button>
          {quote.yours && (
            <button
              onClick={onDelete}
              className="rounded-[4px] px-2 py-1 font-mono text-[10px] text-muted transition-colors hover:text-danger"
            >
              remove
            </button>
          )}
        </span>
      </figcaption>
    </motion.figure>
  )
}

export function Quotes({
  type,
  tmdbId,
  name,
}: {
  type: string
  tmdbId: number
  name: string
}) {
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [body, setBody] = useState('')
  const [character, setCharacter] = useState('')
  const [asked, setAsked] = useState(false)

  const key = ['quotes', type, tmdbId]
  const { data } = useQuery({
    queryKey: key,
    queryFn: () => api.get<{ quotes: Quote[] }>(`/api/titles/${type}/${tmdbId}/quotes`),
    staleTime: 60_000,
  })

  const {
    data: suggested,
    error: suggestError,
    isFetching: suggesting,
  } = useQuery({
    queryKey: ['quote-suggestions', type, tmdbId],
    queryFn: () =>
      api.get<{ suggestions: Suggestion[]; note: string }>(
        `/api/titles/${type}/${tmdbId}/quotes/suggestions`,
      ),
    enabled: asked,
    staleTime: Infinity,
    retry: false,
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: key })

  const add = useMutation({
    mutationFn: (payload: { body: string; character?: string | null }) =>
      api.post(`/api/titles/${type}/${tmdbId}/quotes`, payload),
    onSuccess: () => {
      refresh()
      setBody('')
      setCharacter('')
      setAdding(false)
    },
  })
  const like = useMutation({
    mutationFn: (id: string) => api.post(`/api/quotes/${id}/like`),
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/api/quotes/${id}`),
    onSuccess: refresh,
  })

  const saved = new Set((data?.quotes ?? []).map((q) => q.body.toLowerCase()))
  const fresh = (suggested?.suggestions ?? []).filter((s) => !saved.has(s.text.toLowerCase()))
  const aiOff = suggestError instanceof ApiError && suggestError.status === 503

  return (
    <section className="mt-12 min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Lines worth keeping</h2>
        <div className="flex gap-2">
          {!asked && (
            <button
              onClick={() => setAsked(true)}
              className="rounded-[4px] border border-line px-3.5 py-1.5 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
            >
              Find some
            </button>
          )}
          <button
            onClick={() => setAdding((open) => !open)}
            className={clsx(
              'rounded-[4px] px-3.5 py-1.5 text-sm transition-colors',
              adding
                ? 'border border-ember text-ember'
                : 'bg-ember font-medium text-ink hover:bg-ember/90',
            )}
          >
            {adding ? 'Cancel' : 'Add a line'}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {adding && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="wd-plate mt-4 p-4">
              <textarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder={`The line you remember from ${name}`}
                rows={2}
                className="w-full resize-none bg-transparent font-display text-lg placeholder:font-sans placeholder:text-base placeholder:text-muted focus:outline-none"
              />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  value={character}
                  onChange={(event) => setCharacter(event.target.value)}
                  placeholder="Who says it"
                  className="min-w-0 flex-1 rounded-[4px] border border-line bg-panel-2 px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
                />
                <button
                  onClick={() => add.mutate({ body, character: character || null })}
                  disabled={body.trim().length < 2 || add.isPending}
                  className="shrink-0 rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink disabled:opacity-40"
                >
                  {add.isPending ? 'Saving' : 'Save'}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {asked && (
        <div className="mt-4">
          {suggesting && (
            <motion.p
              animate={{ opacity: [0.35, 1, 0.35] }}
              transition={{ duration: 1.4, repeat: Infinity }}
              className="wd-eyebrow"
            >
              Recalling
            </motion.p>
          )}
          {aiOff && (
            <p className="text-sm text-muted">
              This needs the AI features, which are switched off. You can still add lines
              yourself.
            </p>
          )}
          {fresh.length > 0 && (
            <div className="rounded-md border border-dashed border-line p-4">
              <p className="wd-eyebrow">
                Pick one to keep
              </p>
              <div className="mt-3 flex flex-col gap-2">
                {fresh.map((suggestion) => (
                  <button
                    key={suggestion.text}
                    onClick={() =>
                      add.mutate({ body: suggestion.text, character: suggestion.character })
                    }
                    className="rounded-[4px] px-3 py-2 text-left transition-colors hover:bg-panel-2"
                  >
                    <span className="block font-display">{suggestion.text}</span>
                    {suggestion.character && (
                      <span className="mt-0.5 block font-mono text-[11px] text-muted">
                        {suggestion.character}
                      </span>
                    )}
                  </button>
                ))}
              </div>
              {/* The provenance matters: these are recalled, not transcribed. */}
              <p className="mt-3 text-[11px] text-muted">{suggested?.note}</p>
            </div>
          )}
          {asked && !suggesting && !aiOff && fresh.length === 0 && (
            <p className="text-sm text-muted">
              Nothing came back for this one. Add the line you remember instead.
            </p>
          )}
        </div>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <AnimatePresence mode="popLayout">
          {(data?.quotes ?? []).map((quote) => (
            <QuoteCard
              key={quote.id}
              quote={quote}
              onLike={() => like.mutate(quote.id)}
              onDelete={() => remove.mutate(quote.id)}
            />
          ))}
        </AnimatePresence>
      </div>

      {data && data.quotes.length === 0 && !adding && (
        <p className="mt-4 text-sm text-muted">
          No lines saved yet. Find some, or add the one you remember.
        </p>
      )}
    </section>
  )
}
