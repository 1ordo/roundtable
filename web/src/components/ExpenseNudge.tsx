import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { Link } from 'react-router'
import { api } from '../api/client'

type IdleService = {
  id: number
  name: string
  color: string | null
  last_used: string | null
  days_idle: number
}

/* Dismissing is a real answer, so it holds for a month per service rather
   than resetting on reload. Kept in this browser only: the reminder is a
   nudge about money, not state worth syncing. */
const SNOOZE_DAYS = 30

function snoozeKey(id: number): string {
  return `wd-expense-snooze-${id}`
}

function snoozed(id: number): boolean {
  const until = localStorage.getItem(snoozeKey(id))
  return until !== null && Date.parse(until) > Date.now()
}

/* The ledger: one small card when a paid service has had a silent month.
   It only ever appears for people who switched the reminders on, it names
   one service at a time, and "Not now" means a month of quiet. */
export function ExpenseNudge() {
  const { data } = useQuery({
    queryKey: ['idle-services'],
    queryFn: () =>
      api.get<{ enabled: boolean; services: IdleService[] }>('/api/services/idle'),
    staleTime: 6 * 60 * 60 * 1000,
    retry: false,
  })
  const [put_away, setPutAway] = useState<number[]>([])

  const service = data?.enabled
    ? data.services.find((s) => !snoozed(s.id) && !put_away.includes(s.id))
    : undefined

  function dismiss(id: number) {
    const until = new Date(Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000)
    localStorage.setItem(snoozeKey(id), until.toISOString())
    setPutAway((ids) => [...ids, id])
  }

  return (
    <AnimatePresence>
      {service && (
        <motion.aside
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          aria-label="Subscription reminder"
          className="wd-plate fixed right-4 bottom-20 z-40 w-80 max-w-[calc(100vw-2rem)] p-4 md:bottom-6"
        >
          <p className="wd-eyebrow wd-eyebrow--nitrate !text-[10px]">Your ledger</p>
          <p className="mt-2 font-display text-xl font-semibold uppercase">
            {service.name} has been quiet
          </p>
          <p className="mt-1.5 text-sm text-muted">
            Nothing you logged in the last{' '}
            {service.last_used ? `${service.days_idle} days` : 'month'} used it. If that
            sounds right, pausing it is free.
          </p>
          <div className="mt-3.5 flex items-center gap-2.5">
            <button
              onClick={() => dismiss(service.id)}
              className="rounded-[4px] border border-line bg-panel px-3.5 py-1.5 text-sm transition-colors hover:border-ember hover:text-ember"
            >
              Not now
            </button>
            <Link
              to="/app/settings"
              onClick={() => dismiss(service.id)}
              className="text-sm text-muted transition-colors hover:text-fg"
            >
              Manage services
            </Link>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
