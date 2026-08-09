import { useState } from 'react'
import { motion } from 'motion/react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { img, isNotConfigured, type TitleCard } from '../api/catalog'
import { Row } from '../components/Row'
import { PosterCard } from '../components/PosterCard'
import { LoadError, SetupNotice } from '../components/SetupNotice'

type ServiceOut = {
  id: number
  name: string
  color: string
  note: string | null
  subscribed: boolean
  logo_path: string | null
  tracked: boolean
}

type ServiceSection = { service: ServiceOut; items: TitleCard[]; unknown: boolean }

type NewResponse = {
  rows: { key: string; title: string; items: TitleCard[] }[]
  services: ServiceSection[]
  showing_all_services: boolean
}

function ServiceBlock({ section }: { section: ServiceSection }) {
  const { service, items, unknown } = section
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="min-w-0"
    >
      <div className="mb-3 flex items-center gap-2.5">
        {service.logo_path ? (
          <img
            src={img(service.logo_path, 'w185') ?? ''}
            alt=""
            className="h-7 w-7 rounded-md object-cover"
          />
        ) : (
          <span
            aria-hidden
            className="h-5 w-1.5 rounded-full"
            style={{ backgroundColor: service.color }}
          />
        )}
        <h2 className="font-display text-xl font-semibold uppercase tracking-[0.02em]">
          {service.name}
        </h2>
        {service.note && <span className="text-xs text-muted">{service.note}</span>}
        {!service.subscribed && (
          <span className="rounded-full border border-line px-2 py-0.5 text-[10px] text-muted uppercase">
            not yours
          </span>
        )}
      </div>

      {unknown ? (
        <p className="rounded-md border border-dashed border-line px-4 py-5 text-sm text-muted">
          {service.tracked
            ? `Nothing new on ${service.name} in the last month.`
            : `The catalog carries no listings for ${service.name}, so this cannot be filled in. Everything else on this page still works.`}
        </p>
      ) : (
        <div className="wd-scroller flex gap-4 pb-3">
          {items.map((item, i) => (
            <PosterCard key={`${item.type}-${item.tmdb_id}`} title={item} index={i} />
          ))}
        </div>
      )}
    </motion.section>
  )
}

export function NewPage() {
  const [showAll, setShowAll] = useState(false)
  const { data, error, isLoading } = useQuery({
    queryKey: ['new', showAll],
    queryFn: () => api.get<NewResponse>(`/api/new${showAll ? '?all=true' : ''}`),
    retry: false,
  })

  return (
    <div className="min-w-0">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="wd-eyebrow">Tonight</p>
          <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
            New
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted">
            Fresh arrivals, and what landed on the services you pay for.
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
            className="accent-ember"
          />
          Show every service
        </label>
      </header>

      {error && (
        <div className="mt-8">{isNotConfigured(error) ? <SetupNotice /> : <LoadError />}</div>
      )}

      {isLoading && (
        <div className="mt-8 flex gap-4 overflow-hidden">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="aspect-[2/3] w-36 shrink-0 animate-pulse rounded-lg bg-panel" />
          ))}
        </div>
      )}

      <div className="mt-8 flex flex-col gap-10">
        {data?.rows.map((row) => <Row key={row.key} title={row.title} items={row.items} />)}
      </div>

      {data && data.services.length > 0 && (
        <div className="mt-12">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">
            By service
          </h2>
          <div className="mt-5 flex flex-col gap-10">
            {data.services.map((section) => (
              <ServiceBlock key={section.service.id} section={section} />
            ))}
          </div>
        </div>
      )}

      {data && data.services.length === 0 && (
        <p className="mt-10 rounded-md border border-dashed border-line px-4 py-5 text-sm text-muted">
          You have not picked any services yet. Choose them in{' '}
          <Link to="/app/settings" className="text-ember hover:underline">
            settings
          </Link>{' '}
          and this page will follow them.
        </p>
      )}
    </div>
  )
}
