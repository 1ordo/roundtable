import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { useAuthMethods, usePasswordLogin, useRegister } from '../api/auth'
import { Beams } from '../components/Beams'
import { BeamMark, Wordmark } from '../components/Wordmark'
import { ScreenLoader } from '../components/ScreenLoader'
import { useMe } from '../app/useMe'

const ERROR_COPY: Record<string, string> = {
  denied: 'This account is disabled. Ask your admin to re-enable it.',
  state_mismatch: 'The sign-in attempt expired. Try again.',
  oidc_failed: 'The identity server did not accept the sign-in. Try again.',
  missing_code: 'The identity server sent an incomplete response. Try again.',
  oidc_disabled: 'Passkey sign-in is switched off. Use your username and password.',
  oidc_not_configured: 'No identity server is set up yet. Use your username and password.',
}

export function Login() {
  const { data: me, isLoading } = useMe()
  const { data: methods, isLoading: methodsLoading } = useAuthMethods()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const error = params.get('error')
  const next = params.get('next') ?? '/app'

  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const login = usePasswordLogin()
  const register = useRegister()

  if (isLoading || methodsLoading) return <ScreenLoader />
  if (me) return <Navigate to={next.startsWith('/') ? next : '/app'} replace />

  const showPassword = methods?.password ?? false
  const showOidc = methods?.oidc ?? true
  const busy = login.isPending || register.isPending
  const formError =
    (mode === 'signin' ? login.error?.message : register.error?.message) ?? null

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!username.trim() || !password) return
    const done = { onSuccess: () => navigate(next.startsWith('/') ? next : '/app') }
    if (mode === 'signin') {
      login.mutate({ username: username.trim(), password }, done)
    } else {
      register.mutate({ username: username.trim(), password }, done)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-ink px-6 py-10">
      <Beams />
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="relative w-full max-w-sm"
      >
        <div className="mb-9 flex flex-col items-center gap-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.9, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
          >
            <BeamMark className="h-12 w-12" />
          </motion.div>
          <Wordmark className="text-4xl" />
          <p className="text-center text-sm text-muted">
            Your private screening room. Great picks for one, two, or the whole couch.
          </p>
        </div>

        {error && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            role="alert"
            className="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-fg"
          >
            {ERROR_COPY[error] ?? 'Sign-in failed. Try again.'}
          </motion.p>
        )}

        {showPassword && (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <label className="sr-only" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              className="rounded-[4px] border border-line bg-panel px-4 py-3 text-fg placeholder:text-muted focus:border-ember focus:outline-none"
            />
            <label className="sr-only" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="rounded-[4px] border border-line bg-panel px-4 py-3 text-fg placeholder:text-muted focus:border-ember focus:outline-none"
            />

            <AnimatePresence>
              {formError && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  role="alert"
                  className="text-sm text-danger"
                >
                  {formError}
                </motion.p>
              )}
            </AnimatePresence>

            <motion.button
              type="submit"
              disabled={busy || !username.trim() || !password}
              whileHover={{ scale: busy ? 1 : 1.015 }}
              whileTap={{ scale: busy ? 1 : 0.985 }}
              className="rounded-[4px] bg-ember px-6 py-3.5 font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
            >
              {busy ? 'One moment' : mode === 'signin' ? 'Sign in' : 'Create account'}
            </motion.button>

            {methods?.registration_open && (
              <button
                type="button"
                onClick={() => setMode(mode === 'signin' ? 'register' : 'signin')}
                className="text-center text-xs text-muted transition-colors hover:text-fg"
              >
                {mode === 'signin'
                  ? 'No account yet? Create one'
                  : 'Already have an account? Sign in'}
              </button>
            )}
            {mode === 'register' && (
              <p className="text-center text-xs text-muted">
                Passwords need at least 10 characters.
              </p>
            )}
          </form>
        )}

        {showPassword && showOidc && (
          <div className="my-6 flex items-center gap-3">
            <span className="h-px flex-1 bg-line" />
            <span className="font-mono text-[10px] tracking-[0.2em] text-muted uppercase">
              or
            </span>
            <span className="h-px flex-1 bg-line" />
          </div>
        )}

        {showOidc && (
          <>
            <motion.a
              href={`/auth/login?next=${encodeURIComponent(next)}`}
              whileHover={{ scale: 1.015 }}
              whileTap={{ scale: 0.985 }}
              className={
                showPassword
                  ? 'block w-full rounded-[4px] border border-line bg-panel px-6 py-3.5 text-center font-medium text-fg transition-colors hover:border-ember hover:text-ember'
                  : 'block w-full rounded-[4px] bg-ember px-6 py-3.5 text-center font-medium text-ink transition-colors hover:bg-ember/90'
              }
            >
              Sign in with passkey
            </motion.a>
            <p className="mt-4 text-center text-xs text-muted">
              Passkey sign-in is handled by Pocket ID on your home network.
            </p>
          </>
        )}

        {!showOidc && !showPassword && (
          <p className="wd-plate px-4 py-3 text-center text-sm text-muted">
            No sign-in method is enabled. An admin needs to turn one back on.
          </p>
        )}
      </motion.div>
    </div>
  )
}
