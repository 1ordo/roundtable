import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { isNotConfigured, streamHome, useHome, type HomeRow } from '../api/catalog'
import { Hero } from '../components/Hero'
import { NextUp } from '../components/NextUp'
import { useMe } from '../app/useMe'
import { Row } from '../components/Row'
import { LoadError, SetupNotice } from '../components/SetupNotice'

/* Which shelves the server can produce another page of. Kept as one pattern
   rather than a list, since the genre, language and anchor rows all carry an
   id in their key. */
const PERSONAL = /^(for-you|because-|with-people-you-follow|fresh-for-you|gems-for-you|vintage-for-you|short-for-you|acclaimed-for-you)/

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 5) return 'Late night pick'
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

/* Rows appear one at a time, in reading order, as the server finishes
 * each: a queue, not a curtain. If the stream cannot run at all the old
 * whole-page request takes over, so nothing regresses. */
function useHomeRows() {
  const [rows, setRows] = useState<HomeRow[]>([])
  const [done, setDone] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    streamHome(
      (row) => setRows((current) => [...current, row]),
      controller.signal,
    )
      .then(() => setDone(true))
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => controller.abort()
  }, [])
  return { rows, done, failed }
}

export function Home() {
  const { data: me } = useMe()
  const stream = useHomeRows()
  // The fallback only runs when streaming is not available at all.
  const fallback = useHome(stream.failed)
  const data = stream.failed ? fallback.data : { rows: stream.rows }
  const error = stream.failed ? fallback.error : null
  const isLoading = stream.failed
    ? fallback.isLoading
    : stream.rows.length === 0 && !stream.done
  const streaming = !stream.failed && !stream.done && stream.rows.length > 0

  // The slider draws from the strongest row available: the personal picks
  // when they exist, otherwise whatever leads the page.
  const heroSource =
    data?.rows.find((row) => row.key === 'for-you')?.items ??
    data?.rows.find((row) => row.items.some((i) => i.backdrop_path))?.items ??
    []

  return (
    <div>
      {heroSource.length > 0 ? (
        <Hero items={heroSource} greeting={`${greeting()}, ${me?.user.username ?? ''}`} />
      ) : (
        <header className="mb-8">
          <p className="wd-eyebrow">Tonight</p>
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]"
          >
            {greeting()}, {me?.user.username}
          </motion.h1>
        </header>
      )}

      {isLoading && (
        <div className="flex flex-col gap-8">
          {[0, 1, 2].map((row) => (
            <div key={row}>
              <div className="mb-3 h-6 w-44 animate-pulse rounded bg-panel-2" />
              <div className="flex gap-4 overflow-hidden">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="aspect-[2/3] w-36 shrink-0 animate-pulse rounded-[6px] bg-panel sm:w-40" />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (isNotConfigured(error) ? <SetupNotice /> : <LoadError />)}

      <NextUp />

      <div className="flex flex-col gap-10">
        {data?.rows.map((row) => (
          <Row
            key={row.key}
            title={row.title}
            items={row.items}
            /* Only the personalized shelves can be asked for more of
               themselves. A trending row is a fixed list from upstream, and
               offering to extend it would be a button that does nothing. */
            shelf={PERSONAL.test(row.key) ? row.key : undefined}
          />
        ))}
        {streaming && (
          <div aria-hidden>
            <div className="mb-3 h-6 w-44 animate-pulse rounded bg-panel-2" />
            <div className="flex gap-4 overflow-hidden">
              {[...Array(6)].map((_, i) => (
                <div
                  key={i}
                  className="aspect-[2/3] w-36 shrink-0 animate-pulse rounded-[6px] bg-panel sm:w-40"
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
