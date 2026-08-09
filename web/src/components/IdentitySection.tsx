import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { Link } from 'react-router'
import clsx from 'clsx'
import { ApiError } from '../api/client'
import { useUpdateProfile } from '../api/tracking'
import { useMe } from '../app/useMe'
import { Choice, Row } from './SettingsSections'

const PANELS = [
  { key: 'numbers', label: 'Your numbers', hint: 'Titles watched, hours, and how many you loved.' },
  { key: 'genres', label: 'What you watch', hint: 'Your most watched genres.' },
  { key: 'favourites', label: 'Favourites', hint: 'The ones you rated highest or loved.' },
  { key: 'lists', label: 'Lists', hint: 'The names of your lists and how many are in each.' },
  { key: 'posts', label: 'Posts', hint: 'Everything you have written.' },
]

const LEVELS = [
  { key: 'public', label: 'Everyone' },
  { key: 'friends', label: 'Friends' },
  { key: 'private', label: 'Only me' },
]

export function IdentitySection() {
  const { data: me } = useMe()
  const update = useUpdateProfile()
  const user = me?.user
  const [handle, setHandle] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  // Seed once the profile arrives, not on every render, or typing would be
  // overwritten by each refetch.
  useEffect(() => {
    if (!user) return
    setHandle((current) => current || user.handle || '')
    setDisplayName((current) => current || user.display_name || '')
  }, [user])

  function save() {
    setProblem(null)
    setSaved(false)
    update.mutate(
      { handle: handle.trim(), display_name: displayName.trim() },
      {
        onSuccess: () => setSaved(true),
        onError: (error) =>
          setProblem(
            error instanceof ApiError ? error.message : 'could not save that',
          ),
      },
    )
  }

  const prefs = user?.prefs ?? {}
  const panels = (prefs.panel_visibility as Record<string, string> | undefined) ?? {}
  const profileLevel = (user?.visibility as string) ?? 'friends'

  return (
    <>
      <section className="mt-10">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Your name here</h2>
        <p className="mt-1 text-sm text-muted">
          The handle is how people find you and what appears on everything you write.
        </p>

        <div className="mt-4 flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm">Handle</span>
            <span className="flex items-center gap-2">
              <span className="font-mono text-muted">@</span>
              <input
                value={handle}
                onChange={(e) => setHandle(e.target.value)}
                placeholder="lordo_films"
                className="min-w-0 flex-1 rounded-[4px] border border-line bg-panel px-3 py-2 font-mono text-sm placeholder:text-muted focus:border-ember focus:outline-none"
              />
            </span>
            <span className="text-xs text-muted">
              Letters, numbers and underscores. Three to twenty four characters.
            </span>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm">Display name</span>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Mohamed"
              className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
            />
          </label>

          <div className="flex flex-wrap items-center gap-3">
            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={save}
              disabled={update.isPending || !handle.trim()}
              className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink hover:bg-ember/90 disabled:opacity-40"
            >
              {update.isPending ? 'Saving' : 'Save'}
            </motion.button>
            {user?.handle && (
              <Link
                to={`/app/u/${user.handle}`}
                className="text-sm text-muted transition-colors hover:text-ember"
              >
                See your profile
              </Link>
            )}
            {saved && <span className="text-xs text-nitrate">Saved.</span>}
            {problem && <span className="text-xs text-danger">{problem}</span>}
          </div>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Who sees what</h2>
        <p className="mt-1 text-sm text-muted">
          Your profile is set to {LEVELS.find((l) => l.key === profileLevel)?.label.toLowerCase()}.
          Each part can differ, so you can show your numbers to everyone and keep your lists
          among friends.
        </p>

        <div className="mt-4">
          <Row
            label="Your profile"
            hint="The default for anything you have not set below."
          >
            <Choice
              value={profileLevel}
              onChange={(next) => update.mutate({ visibility: next })}
              options={LEVELS}
            />
          </Row>
          {PANELS.map((panel) => (
            <Row key={panel.key} label={panel.label} hint={panel.hint}>
              <Choice
                value={panels[panel.key] ?? profileLevel}
                onChange={(next) =>
                  update.mutate({
                    panel_visibility: { ...panels, [panel.key]: next },
                  })
                }
                options={LEVELS}
              />
            </Row>
          ))}
        </div>

        <p
          className={clsx(
            'mt-4 rounded-md border border-dashed border-line px-4 py-3 text-xs text-muted',
          )}
        >
          Nothing here is ever visible to the open internet. Everyone means everyone signed in
          to this instance.
        </p>
      </section>
    </>
  )
}
