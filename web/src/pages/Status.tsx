import { motion } from 'motion/react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'

type Service = { name: string; ok: boolean; detail: string }

type Status = {
  healthy: boolean
  services: Service[]
  titles: number
  people_indexed: number
  countries: number
  services_tracked: number
  catalog_fresh_pct: number
  last_sweep: string | null
  version: string
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="wd-plate px-4 py-4">
      <p className="font-display text-3xl tabular-nums">{value}</p>
      <p className="mt-1 font-mono text-[10px] tracking-[0.15em] text-muted uppercase">{label}</p>
    </div>
  )
}

export function Status() {
  const { data, isLoading } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.get<Status>('/api/status'),
    refetchInterval: 60_000,
  })

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-8">
        <p className="wd-eyebrow">The booth</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Status
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          What this instance is running on, and how much of the catalog it holds.
        </p>
      </header>

      {isLoading && <div className="h-32 animate-pulse rounded-md bg-panel" />}

      {data && (
        <>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={clsx(
              'flex items-center gap-3 rounded-md border px-4 py-4',
              data.healthy ? 'border-line bg-panel' : 'border-danger/50 bg-danger/5',
            )}
          >
            <span
              aria-hidden
              className={clsx(
                'h-2.5 w-2.5 shrink-0 rounded-full',
                data.healthy && 'animate-pulse',
              )}
              style={{
                backgroundColor: data.healthy ? 'var(--color-nitrate)' : 'var(--color-danger)',
              }}
            />
            <span className="min-w-0">
              <span className="block text-sm">
                {data.healthy ? 'Everything is running' : 'Something is not answering'}
              </span>
              <span className="block text-xs text-muted">
                {data.healthy
                  ? 'All parts responded to this check.'
                  : 'The list below says which part, and what it reported.'}
              </span>
            </span>
          </motion.div>

          <section className="mt-8">
            <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Parts</h2>
            <ul className="mt-3 overflow-hidden rounded-md border border-line">
              {data.services.map((service, i) => (
                <motion.li
                  key={service.name}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex items-center gap-3 border-t border-line bg-panel px-4 py-3 first:border-t-0"
                >
                  {/* Never colour alone: the word says it too. */}
                  <span
                    aria-hidden
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{
                      backgroundColor: service.ok
                        ? 'var(--color-nitrate)'
                        : 'var(--color-danger)',
                    }}
                  />
                  <span className="min-w-0 flex-1 text-sm">{service.name}</span>
                  <span className="shrink-0 font-mono text-[11px] text-muted">
                    {service.detail}
                  </span>
                  <span
                    className={clsx(
                      'w-14 shrink-0 text-right font-mono text-[11px]',
                      service.ok ? 'text-muted' : 'text-danger',
                    )}
                  >
                    {service.ok ? 'ok' : 'down'}
                  </span>
                </motion.li>
              ))}
            </ul>
          </section>

          <section className="mt-8">
            <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">The catalog</h2>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Figure value={data.titles.toLocaleString()} label="titles" />
              <Figure value={data.people_indexed.toLocaleString()} label="searchable" />
              <Figure value={String(data.countries)} label="countries" />
              <Figure value={String(data.services_tracked)} label="services" />
            </div>
            <div className="mt-4 wd-plate p-4">
              <div className="flex items-baseline justify-between">
                <span className="text-sm">Refreshed in the last month</span>
                <span className="font-mono text-sm text-ember">{data.catalog_fresh_pct}%</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-panel-2">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${data.catalog_fresh_pct}%` }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                  className="h-full rounded-full bg-ember"
                />
              </div>
              <p className="mt-2 text-xs text-muted">
                The crawler keeps working through the rest in the background. Nothing is
                waiting on you.
              </p>
            </div>
          </section>

          <p className="mt-8 font-mono text-[11px] text-muted">
            Checked just now. This page refreshes itself every minute.
          </p>
        </>
      )}
    </div>
  )
}
