import { motion } from 'motion/react'
import clsx from 'clsx'
import { useAuthSettings, useUpdateAuthSettings, type AuthSettings } from '../api/auth'

function Toggle({
  on,
  onClick,
  label,
  disabled,
}: {
  on: boolean
  onClick: () => void
  label: string
  disabled?: boolean
}) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        'relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-40',
        on ? 'bg-ember' : 'bg-panel-2',
      )}
    >
      <motion.span
        layout
        transition={{ type: 'spring', stiffness: 600, damping: 40 }}
        className={clsx(
          'absolute top-0.5 h-5 w-5 rounded-full',
          on ? 'right-0.5 bg-ink' : 'left-0.5 bg-muted',
        )}
      />
    </button>
  )
}

export function AuthSettingsSection() {
  const { data } = useAuthSettings()
  const update = useUpdateAuthSettings()
  if (!data) return null
  const settings = data

  function apply(patch: Partial<AuthSettings>) {
    update.mutate({
      oidc_enabled: settings.oidc_enabled,
      password_enabled: settings.password_enabled,
      registration_open: settings.registration_open,
      ...patch,
    })
  }

  // The last method standing cannot be switched off.
  const lastOne = (which: 'oidc' | 'password') =>
    which === 'oidc'
      ? settings.oidc_enabled && !settings.password_enabled
      : settings.password_enabled && !settings.oidc_enabled

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Sign-in methods</h2>
      <p className="mt-1 text-sm text-muted">
        Turn either method on or off. At least one has to stay on.
      </p>

      <div className="mt-4 flex flex-col gap-2">
        <div className="wd-plate flex items-center gap-4 px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm">Passkey through Pocket ID</p>
            <p className="mt-0.5 text-xs text-muted">
              {data.oidc_configured
                ? 'Identity server is configured.'
                : 'No client id set yet, so this cannot be used until the server is configured.'}
            </p>
          </div>
          <Toggle
            on={data.oidc_enabled}
            disabled={lastOne('oidc')}
            label="Passkey sign-in"
            onClick={() => apply({ oidc_enabled: !data.oidc_enabled })}
          />
        </div>

        <div className="wd-plate flex items-center gap-4 px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm">Username and password</p>
            <p className="mt-0.5 text-xs text-muted">
              Works anywhere, including offline. Set passwords per person below.
            </p>
          </div>
          <Toggle
            on={data.password_enabled}
            disabled={lastOne('password')}
            label="Password sign-in"
            onClick={() => apply({ password_enabled: !data.password_enabled })}
          />
        </div>

        <div
          className={clsx(
            'wd-plate flex items-center gap-4 px-4 py-3 transition-opacity',
            !data.password_enabled && 'opacity-60',
          )}
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm">Open registration</p>
            <p className="mt-0.5 text-xs text-muted">
              Lets anyone who reaches the login page create their own account. Keep this
              off unless you are inviting people.
            </p>
          </div>
          <Toggle
            on={data.registration_open}
            disabled={!data.password_enabled}
            label="Open registration"
            onClick={() => apply({ registration_open: !data.registration_open })}
          />
        </div>
      </div>

      {update.error && <p className="mt-2 text-sm text-danger">{update.error.message}</p>}
    </section>
  )
}
