import { useEffect, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { useSearchParams } from 'react-router'
import clsx from 'clsx'
import { ApiError } from '../api/client'
import { isNotConfigured, useSearch } from '../api/catalog'
import { useAIStatus, useNLSearch } from '../api/ai'
import { PosterCard } from '../components/PosterCard'
import { Icon } from '../components/Icon'
import { LoadError, SetupNotice } from '../components/SetupNotice'
import { PeopleResults } from '../components/PeopleResults'

function ParsedSummary({ parsed }: { parsed: Record<string, unknown> }) {
  const bits: string[] = []
  const genres = parsed.genres as string[] | undefined
  const types = parsed.types as string[] | undefined
  if (types?.length === 1) bits.push(types[0] === 'movie' ? 'films only' : 'series only')
  if (genres?.length) bits.push(genres.join(', ').toLowerCase())
  if (parsed.runtime_max) bits.push(`under ${parsed.runtime_max} min`)
  if (parsed.year_from) bits.push(`from ${parsed.year_from}`)
  if (parsed.year_to) bits.push(`until ${parsed.year_to}`)
  if (parsed.on_shared_services) bits.push('on services you both have')
  if (bits.length === 0) return null
  return (
    <p className="mt-3 font-mono text-xs text-muted">
      Understood as: {String(parsed.mood ?? '')} {bits.length > 0 && `(${bits.join(', ')})`}
    </p>
  )
}

export function Search() {
  const [params, setParams] = useSearchParams()
  const initial = params.get('q') ?? ''
  const [mode, setMode] = useState<'classic' | 'ask'>('classic')
  const [input, setInput] = useState(initial)
  const [query, setQuery] = useState(initial)
  const { data, error, isFetching } = useSearch(mode === 'classic' ? query : '')
  const { data: aiStatus } = useAIStatus()
  const nlSearch = useNLSearch()

  // Debounce typing into the actual query and keep the URL shareable.
  // Only `input` may restart the timer: setParams gets a new identity on
  // every render, and depending on it would reset the countdown forever.
  const setParamsRef = useRef(setParams)
  setParamsRef.current = setParams
  useEffect(() => {
    const handle = setTimeout(() => {
      setQuery(input)
      setParamsRef.current(input ? { q: input } : {}, { replace: true })
    }, 350)
    return () => clearTimeout(handle)
  }, [input])

  function ask() {
    if (input.trim()) nlSearch.mutate(input.trim())
  }

  const askDisabledError =
    nlSearch.error instanceof ApiError && nlSearch.error.status === 503

  const shownResults = mode === 'classic' ? data?.results : nlSearch.data?.results

  return (
    <div>
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="wd-eyebrow">Explore</p>
          <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
            Search
          </h1>
        </div>
        <div className="flex rounded-[4px] border border-line bg-panel p-1">
          {(['classic', 'ask'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={clsx(
                'relative rounded-[4px] px-4 py-1.5 text-sm transition-colors',
                mode === m ? 'text-ink' : 'text-muted hover:text-fg',
              )}
            >
              {mode === m && (
                <motion.span
                  layoutId="search-mode"
                  className="absolute inset-0 rounded-[4px] bg-ember"
                  transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                />
              )}
              <span className="relative">{m === 'classic' ? 'By title' : 'Ask'}</span>
            </button>
          ))}
        </div>
      </header>

      <div className="relative mt-6 max-w-xl">
        <span className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-muted">
          <Icon name="search" />
        </span>
        <input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => mode === 'ask' && e.key === 'Enter' && ask()}
          placeholder={
            mode === 'classic'
              ? 'Search titles'
              : 'Something like Coco but not animated, under 2 hours'
          }
          className="w-full rounded-[4px] border border-line bg-panel py-3 pr-4 pl-12 text-fg placeholder:text-muted focus:border-ember focus:outline-none"
        />
        {mode === 'classic' && isFetching && (
          <span className="absolute top-1/2 right-4 -translate-y-1/2 font-mono text-xs text-muted">
            searching
          </span>
        )}
        {mode === 'ask' && (
          <button
            onClick={ask}
            disabled={nlSearch.isPending || !input.trim()}
            className="absolute top-1/2 right-2 -translate-y-1/2 rounded-[4px] bg-ember px-3.5 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
          >
            {nlSearch.isPending ? 'Thinking' : 'Ask'}
          </button>
        )}
      </div>

      {mode === 'ask' && (
        <>
          <p className="mt-2 text-xs text-muted">
            The answer is ranked by the catalog itself, not invented.
          </p>
          {nlSearch.data && <ParsedSummary parsed={nlSearch.data.parsed} />}
          {askDisabledError && (
            <p className="wd-plate mt-4 px-4 py-3 text-sm text-muted">
              AI features are turned off
              {aiStatus ? '' : ' or not reachable'}. An admin can enable them under
              Admin, AI settings.
            </p>
          )}
          {nlSearch.error && !askDisabledError && (
            <p className="mt-4 text-sm text-danger">
              The AI endpoint did not answer. Try again in a moment.
            </p>
          )}
        </>
      )}

      {mode === 'classic' && error && (
        <div className="mt-8">{isNotConfigured(error) ? <SetupNotice /> : <LoadError />}</div>
      )}

      {mode === 'classic' && (data?.people?.length ?? 0) > 0 && (
        <PeopleResults people={data?.people ?? []} />
      )}

      {mode === 'classic' &&
        data &&
        data.results.length === 0 &&
        (data.people?.length ?? 0) === 0 &&
        query && (
          <p className="mt-10 text-muted">
            Nothing found for that. Try another spelling or the original title.
          </p>
        )}
      {mode === 'ask' && nlSearch.data && nlSearch.data.results.length === 0 && (
        <p className="mt-10 text-muted">
          Nothing in the catalog matches all of that yet. Loosen a constraint or browse
          first so more titles are indexed.
        </p>
      )}

      <div className="mt-8 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {shownResults?.map((title, i) => (
          <div key={`${title.type}-${title.tmdb_id}`} className="[&>div]:w-full">
            <PosterCard title={title} index={i % 12} />
          </div>
        ))}
      </div>
    </div>
  )
}
