import { useState } from 'react'
import { motion } from 'motion/react'
import { Link } from 'react-router'
import { img } from '../api/catalog'
import { useCreateList, useLists, type ListSummary } from '../api/tracking'

const KIND_LABEL: Record<ListSummary['kind'], string> = {
  watchlist: 'Watchlist',
  shared: 'Shared',
  custom: 'Custom',
  // Never rendered: the API filters this kind out of My lists. Present so
  // the map stays exhaustive and a new kind is a compile error, not a blank.
  cinema: 'Cinema',
}

function ListCard({ list, index }: { list: ListSummary; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to={`/app/lists/${list.id}`}
        className="wd-plate wd-plate--hover block p-5"
      >
        <div className="flex h-28 items-center">
          {list.posters.length > 0 ? (
            <div className="flex">
              {list.posters.map((poster, i) => (
                <img
                  key={poster}
                  src={img(poster, 'w185') ?? ''}
                  alt=""
                  className="h-28 w-auto rounded-md border border-line object-cover shadow-lg shadow-black/40"
                  style={{ marginLeft: i === 0 ? 0 : -28, zIndex: 3 - i, rotate: `${(i - 1) * 4}deg` }}
                />
              ))}
            </div>
          ) : (
            <div className="flex h-28 w-full items-center justify-center rounded-md border border-dashed border-line text-sm text-muted">
              Nothing saved yet
            </div>
          )}
        </div>
        <div className="mt-4 flex items-baseline justify-between">
          <p className="font-display text-lg font-semibold uppercase">{list.name}</p>
          <p className="font-mono text-xs text-muted">
            {list.count} {list.count === 1 ? 'title' : 'titles'}
          </p>
        </div>
        <p
          className={
            list.kind === 'shared'
              ? 'mt-1 font-mono text-[10px] tracking-[0.2em] uppercase'
              : 'mt-1 font-mono text-[10px] tracking-[0.2em] text-muted uppercase'
          }
          style={
            list.kind === 'shared'
              ? {
                  background: 'linear-gradient(90deg, var(--color-ember), var(--color-nitrate))',
                  WebkitBackgroundClip: 'text',
                  color: 'transparent',
                }
              : undefined
          }
        >
          {KIND_LABEL[list.kind]}
        </p>
      </Link>
    </motion.div>
  )
}

export function Lists() {
  const { data } = useLists()
  const createList = useCreateList()
  const [name, setName] = useState('')

  function handleCreate() {
    const trimmed = name.trim()
    if (!trimmed) return
    createList.mutate(trimmed, { onSuccess: () => setName('') })
  }

  return (
    <div>
      <header className="mb-8">
        <p className="wd-eyebrow">Your shelf</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          My lists
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          The shared list belongs to both of you. Anything added there shows up for the other
          person too.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.lists.map((list, i) => <ListCard key={list.id} list={list} index={i} />)}

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="flex flex-col justify-center gap-3 rounded-md border border-dashed border-line p-5"
        >
          <p className="font-display text-lg font-semibold uppercase">New list</p>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="Rainy day films"
            className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
          />
          <button
            onClick={handleCreate}
            disabled={!name.trim() || createList.isPending}
            className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-40"
          >
            Create list
          </button>
        </motion.div>
      </div>
    </div>
  )
}
