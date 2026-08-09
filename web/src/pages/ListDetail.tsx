import { Link, useNavigate, useParams } from 'react-router'
import { motion } from 'motion/react'
import { PosterCard } from '../components/PosterCard'
import { useDeleteList, useListItems, useLists } from '../api/tracking'

export function ListDetail() {
  const { listId } = useParams()
  const { data } = useListItems(listId)
  const { data: lists } = useLists()
  const deleteList = useDeleteList()
  const navigate = useNavigate()

  const summary = lists?.lists.find((l) => l.id === listId)
  const isCustom = (data?.kind ?? summary?.kind) === 'custom'

  function handleDelete() {
    if (!listId) return
    if (!window.confirm('Delete this list? Its saved titles stay in the catalog.')) return
    deleteList.mutate(listId, { onSuccess: () => navigate('/app/lists') })
  }

  return (
    <div>
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/app/lists" className="wd-eyebrow transition-colors hover:text-fg">
            Your shelf
          </Link>
          <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
            {data?.name ?? ''}
          </h1>
        </div>
        {isCustom && (
          <button
            onClick={handleDelete}
            className="rounded-[4px] border border-danger/40 px-4 py-2 text-sm text-danger transition-colors hover:bg-danger/10"
          >
            Delete list
          </button>
        )}
      </header>

      {data && data.items.length === 0 && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="max-w-md text-muted"
        >
          Nothing here yet. Open any title and save it to this list.
        </motion.p>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {data?.items.map((item, i) => (
          <div key={`${item.title.type}-${item.title.tmdb_id}`} className="[&>div]:w-full">
            <PosterCard title={item.title} index={i % 12} />
            {item.note && <p className="mt-1 truncate px-0.5 text-xs text-muted">{item.note}</p>}
            {data.kind === 'shared' && item.added_by && (
              <p className="mt-0.5 px-0.5 font-mono text-[10px] text-muted">
                added by {item.added_by}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
