import { useRef, useState } from 'react'
import { motion } from 'motion/react'
import { useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import clsx from 'clsx'
import { postForm } from '../api/client'
import { img } from '../api/catalog'
import { useUpdateProfile } from '../api/tracking'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { CountryPicker } from '../components/CountryPicker'
import { LanguagesSection } from '../components/LanguagesSection'
import { useMe } from '../app/useMe'
import { PasswordSection } from '../components/PasswordSection'
import { TokensSection } from '../components/TokensSection'
import { AlertsSection, MotionSection, SuggestionsSection } from '../components/SettingsSections'
import { IdentitySection } from '../components/IdentitySection'
import { ExtraCountries } from '../components/ExtraCountries'

type Theme = 'dark' | 'light' | 'system'

function applyTheme(theme: Theme) {
  const light =
    theme === 'light' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: light)').matches)
  if (light) document.documentElement.dataset.theme = 'light'
  else delete document.documentElement.dataset.theme
}

function AppearanceSection() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('wd-theme') as Theme) || 'dark',
  )

  function pick(next: Theme) {
    setTheme(next)
    localStorage.setItem('wd-theme', next)
    applyTheme(next)
  }

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Appearance</h2>
      <div className="mt-4 flex rounded-md border border-line bg-panel p-1">
        {(['dark', 'light', 'system'] as const).map((option) => (
          <button
            key={option}
            onClick={() => pick(option)}
            className={clsx(
              'flex-1 rounded-[4px] px-4 py-1.5 text-sm capitalize transition-colors',
              theme === option ? 'bg-ember text-ink' : 'text-muted hover:text-fg',
            )}
          >
            {option}
          </button>
        ))}
      </div>
      <div className="mt-2">
        <MotionSection />
      </div>
    </section>
  )
}

const TABS = [
  { key: 'profile', label: 'Profile' },
  { key: 'watching', label: 'Watching' },
  { key: 'suggestions', label: 'Suggestions' },
  { key: 'alerts', label: 'Alerts' },
  { key: 'account', label: 'Account' },
  { key: 'data', label: 'Data' },
] as const

type Tab = (typeof TABS)[number]['key']

export function Settings() {
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const updateProfile = useUpdateProfile()
  const fileInput = useRef<HTMLInputElement>(null)
  const [tab, setTab] = useState<Tab>('profile')
  const [avatarError, setAvatarError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const user = me?.user
  const country = user?.country_code ?? null
  const services = user?.services ?? []
  const { data: catalogServices } = useQuery({
    queryKey: ['catalog-services'],
    queryFn: () =>
      api.get<
        {
          id: number
          name: string
          color: string
          note: string | null
          logo_path: string | null
        }[]
      >('/api/services'),
  })

  function setCountry(code: string) {
    updateProfile.mutate({ country_code: code })
  }

  function toggleService(providerId: number) {
    const next = services.includes(providerId)
      ? services.filter((s) => s !== providerId)
      : [...services, providerId]
    updateProfile.mutate({ services: next })
  }

  async function handleAvatar(file: File | undefined) {
    if (!file) return
    setAvatarError(null)
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      await postForm('/api/me/avatar', form)
      await queryClient.invalidateQueries({ queryKey: ['me'] })
    } catch (error) {
      setAvatarError(error instanceof Error ? error.message : 'upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <header className="mb-8">
        <p className="wd-eyebrow">The booth</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Settings
        </h1>
      </header>

      {/* Tabs rather than one long scroll: six groups is past the point
          where a person can find anything by scrolling. */}
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'shrink-0 rounded-full border px-3.5 py-1.5 text-sm transition-colors',
              tab === t.key
                ? 'border-ember bg-ember/15 text-ember'
                : 'border-line text-muted hover:text-fg',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <motion.div
        key={tab}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      >
        {tab === 'profile' && (
          <>
            <IdentitySection />
            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Profile picture</h2>
              <div className="mt-4 flex items-center gap-5">
                {user?.avatar_path ? (
                  <img
                    src={user.avatar_path}
                    alt="Your avatar"
                    className="h-20 w-20 rounded-full border border-line object-cover"
                  />
                ) : (
                  <div className="flex h-20 w-20 items-center justify-center rounded-full bg-panel-2 font-display text-2xl text-ember">
                    {user?.username?.slice(0, 1).toUpperCase()}
                  </div>
                )}
                <div>
                  <input
                    ref={fileInput}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={(e) => handleAvatar(e.target.files?.[0])}
                  />
                  <button
                    onClick={() => fileInput.current?.click()}
                    disabled={uploading}
                    className="rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember disabled:opacity-50"
                  >
                    {uploading ? 'Uploading' : 'Upload new picture'}
                  </button>
                  <p className="mt-1.5 text-xs text-muted">
                    JPEG, PNG, or WebP up to 5 MB. Location data is stripped.
                  </p>
                  {avatarError && <p className="mt-1 text-xs text-danger">{avatarError}</p>}
                </div>
              </div>
            </section>

            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Your name</h2>
              <p className="mt-1 text-sm text-muted">
                How you appear to anyone you share a list or a watch night with.
              </p>
              <p className="mt-3 font-display text-2xl">{user?.username}</p>
              <p className="mt-1 font-mono text-xs text-muted">{user?.email}</p>
            </section>

            <AppearanceSection />
          </>
        )}

        {tab === 'watching' && (
          <>
            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Your main country</h2>
              <p className="mt-1 text-sm text-muted">
                The age rating shown on every title, and what the app opens on.
              </p>
              <CountryPicker value={country} onChange={setCountry} />
            </section>

            <ExtraCountries />

            <LanguagesSection />

            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Bring your history</h2>
              <p className="mt-1 text-sm text-muted">
                Import years of Netflix viewing history and your saved list, or paste a list from
                anywhere else.
              </p>
              <Link
                to="/app/import"
                className="mt-4 inline-block rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
              >
                Import
              </Link>
            </section>

            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Your streaming services</h2>
              <p className="mt-1 text-sm text-muted">
                The New page and availability alerts follow these. Pick only what you actually pay
                for.
              </p>
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {(catalogServices ?? []).map((service) => {
                  const active = services.includes(service.id)
                  return (
                    <motion.button
                      key={service.id}
                      whileTap={{ scale: 0.97 }}
                      onClick={() => toggleService(service.id)}
                      aria-pressed={active}
                      className={clsx(
                        'flex items-center gap-2.5 rounded-[4px] border px-3 py-2 text-left text-sm transition-colors',
                        active ? 'border-ember bg-ember/10' : 'border-line hover:border-line/80',
                      )}
                    >
                      {service.logo_path ? (
                        <img
                          src={img(service.logo_path, 'w185') ?? ''}
                          alt=""
                          className="h-7 w-7 shrink-0 rounded-md object-cover"
                        />
                      ) : (
                        <span
                          aria-hidden
                          className="h-6 w-1.5 shrink-0 rounded-full"
                          style={{ backgroundColor: service.color }}
                        />
                      )}
                      <span className="min-w-0">
                        <span className="block truncate">{service.name}</span>
                        {service.note && (
                          <span className="block truncate text-[10px] text-muted">
                            {service.note}
                          </span>
                        )}
                      </span>
                    </motion.button>
                  )
                })}
              </div>
            </section>
          </>
        )}

        {tab === 'suggestions' && <SuggestionsSection />}

        {tab === 'alerts' && <AlertsSection />}

        {tab === 'account' && (
          <>
            <PasswordSection />
            <TokensSection />
          </>
        )}

        {tab === 'data' && (
          <>
            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Bring your history</h2>
              <p className="mt-1 text-sm text-muted">
                Import years of Netflix viewing history and your saved list, or paste a list from
                anywhere else.
              </p>
              <Link
                to="/app/import"
                className="mt-4 inline-block rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
              >
                Import
              </Link>
            </section>

            <section className="mt-10">
              <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Your data</h2>
              <p className="mt-1 text-sm text-muted">Everything is yours to take.</p>
              <div className="mt-4 flex flex-wrap gap-3">
                <a
                  href="/api/export/history.csv"
                  className="rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
                >
                  Download history (CSV)
                </a>
                <a
                  href="/api/export/lists.csv"
                  className="rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
                >
                  Download lists (CSV)
                </a>
                <a
                  href="/api/export/all.json"
                  className="rounded-[4px] border border-line bg-panel px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember"
                >
                  Download everything (JSON)
                </a>
              </div>
            </section>
          </>
        )}
      </motion.div>
    </div>
  )
}
