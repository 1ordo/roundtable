import { useState } from 'react'
import { motion } from 'motion/react'
import { useAuthMethods, useChangePassword } from '../api/auth'

export function PasswordSection() {
  const { data: methods } = useAuthMethods()
  const change = useChangePassword()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saved, setSaved] = useState(false)
  const [mismatch, setMismatch] = useState(false)

  if (!methods?.password) return null

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setSaved(false)
    if (next !== confirm) {
      setMismatch(true)
      return
    }
    setMismatch(false)
    change.mutate(
      { current_password: current || undefined, new_password: next },
      {
        onSuccess: () => {
          setSaved(true)
          setCurrent('')
          setNext('')
          setConfirm('')
        },
      },
    )
  }

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Password</h2>
      <p className="mt-1 text-sm text-muted">
        Used for username and password sign-in. Leave the current field empty if you have
        never set one.
      </p>

      <form onSubmit={submit} className="mt-4 flex max-w-sm flex-col gap-2.5">
        <input
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          placeholder="Current password"
          className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
        />
        <input
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          placeholder="New password, at least 10 characters"
          className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
        />
        <input
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Repeat the new password"
          className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
        />
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={!next || change.isPending}
            className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-40"
          >
            {change.isPending ? 'Saving' : 'Set password'}
          </button>
          {saved && (
            <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-sm text-nitrate">
              Saved
            </motion.span>
          )}
        </div>
        {mismatch && <p className="text-sm text-danger">Those two passwords do not match.</p>}
        {change.error && <p className="text-sm text-danger">{change.error.message}</p>}
      </form>
    </section>
  )
}
