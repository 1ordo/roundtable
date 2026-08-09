import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Link } from 'react-router'
import clsx from 'clsx'
import { useCreateImport, useImports, type ImportBatch } from '../api/imports'

type ServiceKey = 'netflix_history' | 'netflix_mylist' | 'json' | 'manual'

const SERVICES: { key: ServiceKey; name: string; blurb: string }[] = [
  {
    key: 'netflix_history',
    name: 'Netflix viewing history',
    blurb: 'Everything you have watched, with dates. Lands in History.',
  },
  {
    key: 'netflix_mylist',
    name: 'Netflix My List',
    blurb: 'Your saved list from the account export. Lands in your watchlist.',
  },
  {
    key: 'json',
    name: 'Paste a list',
    blurb: 'A JSON array of titles from anywhere else. You choose where it lands.',
  },
  {
    key: 'manual',
    name: 'Search and add',
    blurb: 'OSN+, Shahid, and most regional services have no export. Add fast by search.',
  },
]

function Guide({ service }: { service: ServiceKey }) {
  if (service === 'netflix_history') {
    return (
      <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-fg/90">
        <li>Open netflix.com in a browser and sign in.</li>
        <li>Go to Account, then pick your profile under Profile and Parental Controls.</li>
        <li>Open Viewing activity.</li>
        <li>Scroll to the bottom and use Download all.</li>
        <li>Upload the NetflixViewingHistory.csv file here.</li>
      </ol>
    )
  }
  if (service === 'netflix_mylist') {
    return (
      <div className="mt-4 text-sm text-fg/90">
        <ol className="list-decimal space-y-2 pl-5">
          <li>Open netflix.com, go to Account, then Security.</li>
          <li>Choose Personal information access, then Request a copy of your information.</li>
          <li>Netflix emails a download link within a day or so.</li>
          <li>Inside the archive, find MyList.csv and upload it here.</li>
        </ol>
        <p className="mt-3 text-muted">
          The same archive also contains ViewingActivity.csv, which works in the viewing
          history importer.
        </p>
      </div>
    )
  }
  if (service === 'json') {
    return (
      <div className="mt-4 text-sm text-fg/90">
        <p>Paste a JSON array. Only title is required:</p>
        <pre className="mt-2 overflow-x-auto rounded-lg border border-line bg-ink p-3 font-mono text-xs text-muted">
{`[
  {"title": "Coco", "year": 2017, "type": "movie"},
  {"title": "Dark", "type": "tv", "watched_at": "2024-02-01"}
]`}
        </pre>
      </div>
    )
  }
  return (
    <p className="mt-4 text-sm text-fg/90">
      Most regional platforms (OSN+, Shahid, Watch iT) do not offer exports. The fastest
      path is search: open{' '}
      <Link to="/app/search" className="text-ember underline-offset-4 hover:underline">
        Search
      </Link>
      , find each title, and use the buttons on its page to save it to a list or mark it
      watched.
    </p>
  )
}

const STATUS_COPY: Record<ImportBatch['status'], string> = {
  pending: 'Waiting',
  processing: 'Matching titles',
  review: 'Needs review',
  done: 'Done',
  failed: 'Failed',
}

function BatchRow({ batch }: { batch: ImportBatch }) {
  const stats = batch.stats
  return (
    <div className="wd-plate flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">
          {batch.filename ?? SERVICES.find((s) => s.key === batch.service)?.name ?? batch.service}
        </p>
        <p className="mt-0.5 font-mono text-xs text-muted">
          {new Date(batch.created_at).toLocaleString()} - {stats.total ?? 0} rows
          {stats.imported != null && `, ${stats.imported} imported`}
          {stats.unmatched != null && stats.unmatched > 0 && `, ${stats.unmatched} not found`}
        </p>
        {batch.error && <p className="mt-0.5 text-xs text-danger">{batch.error}</p>}
      </div>
      {(batch.status === 'pending' || batch.status === 'processing') && (
        <motion.span
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.4, repeat: Infinity }}
          className="font-mono text-xs text-ember uppercase"
        >
          {STATUS_COPY[batch.status]}
        </motion.span>
      )}
      {batch.status === 'review' && (
        <Link
          to={`/app/import/${batch.id}`}
          className="rounded-[4px] border border-ember/60 px-3 py-1.5 text-xs text-ember transition-colors hover:bg-ember/10"
        >
          Review {batch.pending_review} {batch.pending_review === 1 ? 'match' : 'matches'}
        </Link>
      )}
      {batch.status === 'done' && (
        <span className="font-mono text-xs text-muted uppercase">Done</span>
      )}
      {batch.status === 'failed' && (
        <span className="font-mono text-xs text-danger uppercase">Failed</span>
      )}
    </div>
  )
}

export function ImportPage() {
  const [service, setService] = useState<ServiceKey>('netflix_history')
  const [jsonText, setJsonText] = useState('')
  const [jsonTarget, setJsonTarget] = useState<'watchlist' | 'history'>('watchlist')
  const [message, setMessage] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const createImport = useCreateImport()
  const { data: batches } = useImports()

  function upload(file: File | undefined) {
    if (!file) return
    setMessage(null)
    createImport.mutate(
      { service, file },
      {
        onSuccess: () => setMessage('Upload received. Matching runs in the background.'),
        onError: (error) => setMessage(error.message),
      },
    )
    if (fileInput.current) fileInput.current.value = ''
  }

  function submitJson() {
    if (!jsonText.trim()) return
    setMessage(null)
    createImport.mutate(
      { service: 'json', payload: jsonText, target: jsonTarget },
      {
        onSuccess: () => {
          setMessage('List received. Matching runs in the background.')
          setJsonText('')
        },
        onError: (error) => setMessage(error.message),
      },
    )
  }

  return (
    <div className="max-w-3xl">
      <header className="mb-8">
        <p className="wd-eyebrow">The booth</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Import
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          Bring your history and lists from other services. Titles are matched against the
          catalog; anything uncertain waits for your confirmation.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        {SERVICES.map((s) => (
          <button
            key={s.key}
            onClick={() => setService(s.key)}
            className={clsx(
              'rounded-md border p-4 text-left transition-colors',
              service === s.key ? 'border-ember bg-ember/10' : 'border-line bg-panel hover:border-line/70',
            )}
          >
            <p className="font-display">{s.name}</p>
            <p className="mt-1 text-xs text-muted">{s.blurb}</p>
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={service}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
          className="mt-6 wd-plate p-5"
        >
          <p className="font-display text-lg font-semibold uppercase">
            {SERVICES.find((s) => s.key === service)?.name}
          </p>
          <Guide service={service} />

          {(service === 'netflix_history' || service === 'netflix_mylist') && (
            <div className="mt-5">
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => upload(e.target.files?.[0])}
              />
              <button
                onClick={() => fileInput.current?.click()}
                disabled={createImport.isPending}
                className="rounded-[4px] bg-ember px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
              >
                {createImport.isPending ? 'Uploading' : 'Upload CSV'}
              </button>
            </div>
          )}

          {service === 'json' && (
            <div className="mt-5">
              <textarea
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                rows={6}
                placeholder='[{"title": "Coco"}]'
                className="w-full rounded-[4px] border border-line bg-ink p-3 font-mono text-sm placeholder:text-muted focus:border-ember focus:outline-none"
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <div className="flex rounded-md border border-line p-1">
                  {(['watchlist', 'history'] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setJsonTarget(t)}
                      className={clsx(
                        'rounded-[4px] px-3 py-1 text-xs transition-colors',
                        jsonTarget === t ? 'bg-ember text-ink' : 'text-muted hover:text-fg',
                      )}
                    >
                      {t === 'watchlist' ? 'To watchlist' : 'To history'}
                    </button>
                  ))}
                </div>
                <button
                  onClick={submitJson}
                  disabled={!jsonText.trim() || createImport.isPending}
                  className="rounded-[4px] bg-ember px-5 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
                >
                  Import
                </button>
              </div>
            </div>
          )}

          {message && <p className="mt-4 text-sm text-nitrate">{message}</p>}
        </motion.div>
      </AnimatePresence>

      {batches && batches.length > 0 && (
        <section className="mt-10">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
            Your imports
          </h2>
          <div className="mt-4 flex flex-col gap-2">
            {batches.map((batch) => (
              <BatchRow key={batch.id} batch={batch} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
