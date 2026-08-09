import { motion } from 'motion/react'
import clsx from 'clsx'
import { useUpdateProfile } from '../api/tracking'
import { useMe } from '../app/useMe'
import { BrowserAlertsSection } from './BrowserAlerts'

/* One row: a label, a sentence of why it matters, and the control. Every
   setting here changes behaviour on the server, so none of them need a
   save button: the change is the request. */
export function Row({
  label,
  hint,
  children,
}: {
  label: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 border-t border-line py-4 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm">{label}</p>
        <p className="mt-0.5 text-xs text-muted">{hint}</p>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

export function Toggle({
  on,
  onChange,
  label,
}: {
  on: boolean
  onChange: (next: boolean) => void
  label: string
}) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className={clsx(
        'flex h-6 w-11 items-center rounded-full px-0.5 transition-colors',
        on ? 'bg-ember' : 'bg-panel-2',
      )}
    >
      <motion.span
        layout
        transition={{ type: 'spring', stiffness: 600, damping: 38 }}
        className={clsx(
          'block h-5 w-5 rounded-full',
          on ? 'ml-auto bg-ink' : 'mr-auto bg-muted',
        )}
      />
    </button>
  )
}

export function Choice<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { key: T; label: string }[]
  value: T
  onChange: (next: T) => void
}) {
  return (
    <div className="flex rounded-md border border-line bg-panel p-1">
      {options.map((option) => (
        <button
          key={option.key}
          onClick={() => onChange(option.key)}
          className={clsx(
            'rounded-[4px] px-3 py-1 text-xs transition-colors',
            value === option.key ? 'bg-ember text-ink' : 'text-muted hover:text-fg',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

// Every switchable kind, and only kinds the API actually sends. This list
// must match NOTIFY_KINDS in api/app/routers/profile.py. It is an allowlist
// on the server, so a kind missing here is a kind that gets muted the moment
// anyone touches this screen. Two entries here once named kinds nothing
// emitted, while the real ones were absent, which silently switched off
// friend requests, watch night invites, surveys, cinema alerts and messages.
const ALERT_KINDS = [
  { key: 'availability', label: 'Now streaming', hint: 'A tracked title lands on your services.' },
  { key: 'episode', label: 'New episode', hint: 'A show you are watching puts one out.' },
  { key: 'franchise', label: 'New in a franchise', hint: 'Another part of something you enjoyed.' },
  { key: 'cinema', label: 'Opening in cinemas', hint: 'A film on your cinema list, a week ahead.' },
  { key: 'person', label: 'Someone you follow', hint: 'A new credit for a person you follow.' },
  { key: 'social', label: 'Reactions and replies', hint: 'Someone likes, replies to or shares your post.' },
  { key: 'message', label: 'Direct messages', hint: 'A friend writes to you.' },
  { key: 'friend_request', label: 'Friend requests', hint: 'Someone asks, or accepts.' },
  { key: 'night_invite', label: 'Watch night invites', hint: 'You are invited, or someone answers.' },
  { key: 'night_survey', label: 'After a watch night', hint: 'Being asked what you thought.' },
]

export function SuggestionsSection() {
  const { data: me } = useMe()
  const update = useUpdateProfile()
  const prefs = me?.user?.prefs ?? {}
  const discovery = (prefs.discovery as string) ?? 'balanced'
  const defaultType = (prefs.default_type as string) ?? 'all'

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Suggestions</h2>
      <p className="mt-1 text-sm text-muted">
        How the algorithm treats you. These take effect on the next page load.
      </p>
      <div className="mt-4">
        <Row
          label="How adventurous"
          hint="Comfort stays near what you already like. Adventurous spends a third of every shelf on things outside it."
        >
          <Choice
            value={discovery}
            onChange={(next) => update.mutate({ discovery: next })}
            options={[
              { key: 'comfort', label: 'Comfort' },
              { key: 'balanced', label: 'Balanced' },
              { key: 'adventurous', label: 'Bold' },
            ]}
          />
        </Row>
        <Row
          label="Hide what you have watched"
          hint="Keeps seen titles out of every shelf, not just the personalized ones."
        >
          <Toggle
            on={Boolean(prefs.hide_watched)}
            onChange={(next) => update.mutate({ hide_watched: next })}
            label="Hide watched titles"
          />
        </Row>
        <Row
          label="Only what you can actually watch"
          hint="Keeps suggestions to the services you subscribe to, in a country you have set. On by default. It needs both, so it does nothing until you have picked your services."
        >
          <Toggle
            // On unless they have turned it off. Boolean() would read an
            // absent preference as off, which is the opposite of the default.
            on={prefs.only_my_services !== false}
            onChange={(next) => update.mutate({ only_my_services: next })}
            label="Only my services"
          />
        </Row>
        <Row label="Open on" hint="Which media type Browse starts with.">
          <Choice
            value={defaultType}
            onChange={(next) => update.mutate({ default_type: next })}
            options={[
              { key: 'all', label: 'Both' },
              { key: 'movie', label: 'Films' },
              { key: 'tv', label: 'Series' },
            ]}
          />
        </Row>
        <Row
          label="Age ratings and parents guide"
          hint="Shows certifications and the content breakdown on every title."
        >
          <Toggle
            on={Boolean(prefs.parents_guide)}
            onChange={(next) => update.mutate({ parents_guide: next })}
            label="Show the parents guide"
          />
        </Row>
      </div>
    </section>
  )
}

export function AlertsSection() {
  const { data: me } = useMe()
  const update = useUpdateProfile()
  const prefs = me?.user?.prefs ?? {}
  // No stored list means everything is on: the default is not a subset.
  const chosen = (prefs.notify_kinds as string[] | undefined) ?? ALERT_KINDS.map((k) => k.key)

  function toggle(kind: string, on: boolean) {
    const next = on ? [...new Set([...chosen, kind])] : chosen.filter((k) => k !== kind)
    update.mutate({ notify_kinds: next })
  }

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Alerts</h2>
      <p className="mt-1 text-sm text-muted">
        Switched off means never created, so nothing piles up unread.
      </p>
      <div className="mt-4">
        <BrowserAlertsSection />
        <Row
          label="Email"
          hint="Sent to the address on your account. Needs an email key set on this instance."
        >
          <Toggle
            on={Boolean(prefs.email_alerts)}
            onChange={(next) => update.mutate({ email_alerts: next })}
            label="Email alerts"
          />
        </Row>
        <Row
          label="Unused subscriptions"
          hint="A word when a service you pay for goes a month without a single watch. Off unless you ask."
        >
          <Toggle
            on={Boolean(prefs.expense_alerts)}
            onChange={(next) => update.mutate({ expense_alerts: next })}
            label="Unused subscription reminders"
          />
        </Row>
        {ALERT_KINDS.map((kind) => (
          <Row key={kind.key} label={kind.label} hint={kind.hint}>
            <Toggle
              on={chosen.includes(kind.key)}
              onChange={(next) => toggle(kind.key, next)}
              label={kind.label}
            />
          </Row>
        ))}
      </div>
    </section>
  )
}

export function MotionSection() {
  const { data: me } = useMe()
  const update = useUpdateProfile()
  const prefs = me?.user?.prefs ?? {}
  const reduced = Boolean(prefs.reduce_motion)

  function set(next: boolean) {
    update.mutate({ reduce_motion: next })
    // Applied immediately: a motion setting that needs a reload to take
    // effect is the wrong way round.
    document.documentElement.dataset.reduceMotion = next ? 'true' : ''
  }

  return (
    <Row
      label="Reduce motion"
      hint="Turns off slides and crossfades. Your system setting is already respected; this adds to it."
    >
      <Toggle on={reduced} onChange={set} label="Reduce motion" />
    </Row>
  )
}
