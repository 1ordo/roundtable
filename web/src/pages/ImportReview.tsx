import { AnimatePresence, motion } from 'motion/react'
import { Link, useParams } from 'react-router'
import { img } from '../api/catalog'
import {
  useDismissImport,
  useImportDetail,
  useResolveImport,
  type ReviewEntry,
} from '../api/imports'

function ReviewCard({ entry, batchId }: { entry: ReviewEntry; batchId: string }) {
  const resolve = useResolveImport(batchId)
  const dismiss = useDismissImport(batchId)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="wd-plate p-4"
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-display text-lg">{entry.name}</p>
        <p className="truncate font-mono text-xs text-muted">from: {entry.raw}</p>
      </div>

      <div className="wd-scroller mt-3 flex gap-3 pb-2">
        {entry.candidates.map((candidate) => (
          <button
            key={`${candidate.type}-${candidate.tmdb_id}`}
            onClick={() =>
              resolve.mutate({
                index: entry.index,
                tmdb_id: candidate.tmdb_id,
                type: candidate.type,
              })
            }
            disabled={resolve.isPending}
            className="group w-28 shrink-0 text-left"
          >
            {candidate.poster_path ? (
              <img
                src={img(candidate.poster_path, 'w185') ?? ''}
                alt={candidate.name}
                className="aspect-[2/3] w-full rounded-lg border border-line object-cover transition-transform group-hover:scale-[1.03] group-hover:border-ember"
              />
            ) : (
              <div className="flex aspect-[2/3] w-full items-center justify-center rounded-lg border border-line bg-panel-2 p-2 text-center text-xs text-muted transition-colors group-hover:border-ember">
                {candidate.name}
              </div>
            )}
            <p className="mt-1.5 truncate text-xs">{candidate.name}</p>
            <p className="font-mono text-[10px] text-muted">
              {candidate.type === 'movie' ? 'Film' : 'Series'}
              {candidate.year ? ` ${candidate.year}` : ''}
            </p>
          </button>
        ))}
      </div>

      <button
        onClick={() => dismiss.mutate({ index: entry.index })}
        disabled={dismiss.isPending}
        className="mt-3 text-xs text-muted transition-colors hover:text-danger"
      >
        None of these, skip it
      </button>
    </motion.div>
  )
}

export function ImportReview() {
  const { batchId = '' } = useParams()
  const { data } = useImportDetail(batchId)

  return (
    <div className="max-w-3xl">
      <Link to="/app/import" className="text-sm text-muted transition-colors hover:text-fg">
        Import
      </Link>
      <header className="mt-3 mb-8">
        <p className="wd-eyebrow">The booth</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Review matches
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          These rows matched more than one title. Pick the right one; skipped rows are left
          out of your data.
        </p>
      </header>

      {data && data.review_queue.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="wd-plate p-6"
        >
          <p className="font-display text-lg font-semibold uppercase">All done</p>
          <p className="mt-1 text-sm text-muted">
            Everything in this import has been settled. Your{' '}
            <Link to="/app/history" className="text-ember hover:underline">
              history
            </Link>{' '}
            and{' '}
            <Link to="/app/lists" className="text-ember hover:underline">
              lists
            </Link>{' '}
            are up to date.
          </p>
        </motion.div>
      )}

      <div className="flex flex-col gap-4">
        <AnimatePresence>
          {data?.review_queue.map((entry) => (
            <ReviewCard key={entry.index} entry={entry} batchId={batchId} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
