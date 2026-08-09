import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'

type AdminUser = {
  id: string
  username: string
  email: string | null
  role: string
  is_active: boolean
  api_enabled: boolean
  country_code: string | null
  last_login_at: string | null
  has_oidc: boolean
}

export function UsersSection() {
  const queryClient = useQueryClient()
  const { data: users } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api.get<AdminUser[]>('/api/admin/users'),
  })
  const [newUsername, setNewUsername] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [error, setError] = useState<string | null>(null)

  const patch = useMutation({
    mutationFn: (input: { id: string; body: Record<string, unknown> }) =>
      api.patch<AdminUser>(`/api/admin/users/${input.id}`, input.body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
    onError: (e) => setError(e.message),
  })
  const [freshPassword, setFreshPassword] = useState<{ username: string; password: string } | null>(
    null,
  )
  const setPassword = useMutation({
    mutationFn: (input: { id: string; username: string }) => {
      // Generated here, shown once, never stored anywhere else.
      const raw = crypto.getRandomValues(new Uint8Array(12))
      const password = btoa(String.fromCharCode(...raw)).replaceAll('+', '-').replaceAll('/', '.')
      return api
        .put(`/api/admin/users/${input.id}/password`, { password })
        .then(() => ({ username: input.username, password }))
    },
    onSuccess: (fresh) => {
      setError(null)
      setFreshPassword(fresh)
    },
    onError: (e) => setError(e.message),
  })
  const create = useMutation({
    mutationFn: () =>
      api.post<AdminUser>('/api/admin/users', {
        username: newUsername,
        email: newEmail || null,
      }),
    onSuccess: () => {
      setNewUsername('')
      setNewEmail('')
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
    onError: (e) => setError(e.message),
  })

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">People</h2>
      <p className="mt-1 text-sm text-muted">
        Accounts link to Pocket ID by username or email on first sign-in, or
        hand out a password from here.
      </p>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      <div className="mt-4 flex flex-col gap-2">
        {users?.map((user) => (
          <div
            key={user.id}
            className="wd-plate flex flex-wrap items-center gap-3 px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">
                {user.username}
                <span
                  className={clsx(
                    'ml-2 font-mono text-[10px] uppercase',
                    user.role === 'admin' ? 'text-ember' : 'text-muted',
                  )}
                >
                  {user.role}
                </span>
                {!user.has_oidc && (
                  <span className="ml-2 font-mono text-[10px] text-nitrate uppercase">
                    awaiting first login
                  </span>
                )}
              </p>
              <p className="truncate font-mono text-xs text-muted">
                {user.email ?? 'no email'}
                {user.last_login_at &&
                  `, last seen ${new Date(user.last_login_at).toLocaleDateString()}`}
              </p>
            </div>
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted">
              <input
                type="checkbox"
                checked={user.api_enabled}
                onChange={(e) =>
                  patch.mutate({ id: user.id, body: { api_enabled: e.target.checked } })
                }
                className="accent-ember"
              />
              API
            </label>
            <button
              onClick={() => setPassword.mutate({ id: user.id, username: user.username })}
              disabled={setPassword.isPending}
              className="rounded-[4px] border border-line px-3 py-1.5 text-xs text-muted transition-colors hover:border-ember hover:text-ember disabled:opacity-50"
            >
              Set password
            </button>
            <button
              onClick={() => patch.mutate({ id: user.id, body: { is_active: !user.is_active } })}
              className={clsx(
                'rounded-[4px] border px-3 py-1.5 text-xs transition-colors',
                user.is_active
                  ? 'border-line text-muted hover:border-danger hover:text-danger'
                  : 'border-nitrate/60 text-nitrate',
              )}
            >
              {user.is_active ? 'Disable' : 'Enable'}
            </button>
          </div>
        ))}
      </div>

      <AnimatePresence>
        {freshPassword && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-4 rounded-[4px] border border-ember/50 bg-ember/10 p-4"
          >
            <p className="wd-eyebrow wd-eyebrow--ember">One-time password</p>
            <p className="mt-2 text-sm">
              {freshPassword.username} signs in with{' '}
              <code className="rounded-[3px] bg-ink px-2 py-0.5 font-mono text-sm">
                {freshPassword.password}
              </code>
            </p>
            <p className="mt-1 text-xs text-muted">
              It shows once. Hand it over, and they change it in Settings.
            </p>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => navigator.clipboard.writeText(freshPassword.password)}
                className="rounded-[4px] border border-line bg-panel px-3 py-1.5 text-xs transition-colors hover:border-ember hover:text-ember"
              >
                Copy
              </button>
              <button
                onClick={() => setFreshPassword(null)}
                className="rounded-[4px] px-3 py-1.5 text-xs text-muted transition-colors hover:text-fg"
              >
                Done
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
          placeholder="Username"
          className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
        />
        <input
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          placeholder="Email (optional)"
          className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
        />
        <button
          onClick={() => create.mutate()}
          disabled={!newUsername.trim() || create.isPending}
          className="rounded-[4px] border border-line px-4 py-2 text-sm transition-colors hover:border-ember hover:text-ember disabled:opacity-40"
        >
          Pre-create account
        </button>
      </div>
    </section>
  )
}

type Flag = { key: string; enabled: boolean; description: string }

export function FlagsSection() {
  const queryClient = useQueryClient()
  const { data: flags } = useQuery({
    queryKey: ['admin-flags'],
    queryFn: () => api.get<Flag[]>('/api/admin/flags'),
  })
  const toggle = useMutation({
    mutationFn: (flag: Flag) =>
      api.put<Flag>(`/api/admin/flags/${flag.key}`, { enabled: !flag.enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-flags'] })
      queryClient.invalidateQueries({ queryKey: ['tokens'] })
    },
  })

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Feature flags</h2>
      <div className="mt-4 flex flex-col gap-2">
        {flags?.map((flag) => (
          <div
            key={flag.key}
            className="wd-plate flex items-center gap-4 px-4 py-3"
          >
            <div className="min-w-0 flex-1">
              <p className="font-mono text-sm">{flag.key}</p>
              <p className="mt-0.5 text-xs text-muted">{flag.description}</p>
            </div>
            <button
              role="switch"
              aria-checked={flag.enabled}
              onClick={() => toggle.mutate(flag)}
              className={clsx(
                'relative h-6 w-11 shrink-0 rounded-full transition-colors',
                flag.enabled ? 'bg-ember' : 'bg-panel-2',
              )}
            >
              <span
                className={clsx(
                  'absolute top-0.5 h-5 w-5 rounded-full transition-all',
                  flag.enabled ? 'left-[22px] bg-ink' : 'left-0.5 bg-muted',
                )}
              />
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}

type AuditRow = {
  id: string
  action: string
  actor_user_id: string | null
  actor: string | null
  summary: string
  category: string
  object_type: string | null
  object_id: string | null
  ip: string | null
  detail: Record<string, unknown> | null
  created_at: string
}

const CATEGORIES = [
  { key: '', label: 'Everything' },
  { key: 'auth', label: 'Sign-ins' },
  { key: 'admin', label: 'Admin' },
  { key: 'profile', label: 'Profiles' },
  { key: 'api', label: 'API' },
  { key: 'data', label: 'Data' },
  { key: 'social', label: 'Social' },
  { key: 'social', label: 'Social' },
]

/* Colour carries the group, but never alone: the tab is labelled and the
   row keeps its plain sentence. */
const CATEGORY_TONE: Record<string, string> = {
  auth: 'text-nitrate',
  admin: 'text-ember',
  api: 'text-fg',
}

function relative(iso: string): string {
  const then = new Date(iso).getTime()
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`
  return new Date(iso).toLocaleDateString()
}

function AuditEntry({ row }: { row: AuditRow }) {
  const [open, setOpen] = useState(false)
  const hasDetail = row.detail != null && Object.keys(row.detail).length > 0
  return (
    <li className="border-t border-line first:border-t-0">
      <button
        onClick={() => hasDetail && setOpen(!open)}
        className={`flex w-full items-start gap-3 px-4 py-3 text-left ${hasDetail ? 'hover:bg-panel-2' : 'cursor-default'}`}
      >
        <span
          className={`mt-1 shrink-0 font-mono text-[10px] tracking-wider uppercase ${CATEGORY_TONE[row.category] ?? 'text-muted'}`}
        >
          {row.category}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm">{row.summary}</span>
          <span className="mt-0.5 block font-mono text-[11px] text-muted">
            {row.action}
            {row.ip ? ` from ${row.ip}` : ''}
          </span>
        </span>
        <span
          className="shrink-0 font-mono text-[11px] text-muted"
          title={new Date(row.created_at).toLocaleString()}
        >
          {relative(row.created_at)}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && hasDetail && (
          <motion.pre
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden bg-panel-2 px-4 font-mono text-[11px] break-all whitespace-pre-wrap text-muted"
          >
            <span className="block py-3">{JSON.stringify(row.detail, null, 2)}</span>
          </motion.pre>
        )}
      </AnimatePresence>
    </li>
  )
}

export function AuditSection() {
  const [category, setCategory] = useState('')
  const [action, setAction] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 25
  const { data } = useQuery({
    queryKey: ['admin-audit', action, category, offset],
    queryFn: () =>
      api.get<{ total: number; rows: AuditRow[]; actions: string[] }>(
        `/api/admin/audit?limit=${limit}&offset=${offset}` +
          (action ? `&action=${action}` : '') +
          (category ? `&category=${category}` : ''),
      ),
  })

  function pick(next: string) {
    setCategory(next)
    setAction('')
    setOffset(0)
  }

  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Audit log</h2>
        <select
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setOffset(0)
          }}
          className="rounded-[4px] border border-line bg-panel px-3 py-1.5 font-mono text-xs focus:border-ember focus:outline-none"
        >
          <option value="">Any action</option>
          {data?.actions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {CATEGORIES.map((tab) => (
          <button
            key={tab.key}
            onClick={() => pick(tab.key)}
            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
              category === tab.key
                ? 'border-ember bg-ember/10 text-ember'
                : 'border-line text-muted hover:text-fg'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <ul className="mt-4 overflow-hidden rounded-md border border-line">
        {data?.rows.length === 0 && (
          <li className="px-4 py-8 text-center text-sm text-muted">Nothing here yet.</li>
        )}
        {data?.rows.map((row) => (
          <AuditEntry key={row.id} row={row} />
        ))}
      </ul>

      {data && data.total > limit && (
        <div className="mt-3 flex items-center justify-center gap-4">
          <button
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="rounded-[4px] border border-line px-4 py-1.5 text-xs text-muted hover:text-fg disabled:opacity-40"
          >
            Newer
          </button>
          <span className="font-mono text-xs text-muted">
            {offset + 1} to {Math.min(offset + limit, data.total)} of {data.total}
          </span>
          <button
            onClick={() => setOffset(offset + limit)}
            disabled={offset + limit >= data.total}
            className="rounded-[4px] border border-line px-4 py-1.5 text-xs text-muted hover:text-fg disabled:opacity-40"
          >
            Older
          </button>
        </div>
      )}
    </section>
  )
}

type Activity = {
  by_kind_30d: Record<string, number>
  per_user: Record<string, unknown>[]
  top_viewed: { name: string; count: number }[]
  top_liked: { name: string; count: number }[]
}

const KIND_LABEL: Record<string, string> = {
  view: 'title views',
  click_out: 'click-outs',
  like: 'likes',
  dislike: 'dislikes',
  watched: 'watches logged',
}

export function ActivitySection() {
  const { data } = useQuery({
    queryKey: ['admin-activity'],
    queryFn: () => api.get<Activity>('/api/admin/activity'),
  })
  if (!data) return null
  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">What the algorithm is learning</h2>
      <p className="mt-1 text-sm text-muted">Signals collected in the last 30 days.</p>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {Object.entries(KIND_LABEL).map(([kind, label]) => (
          <div key={kind} className="wd-plate px-4 py-3">
            <p className="font-mono text-2xl">{data.by_kind_30d[kind] ?? 0}</p>
            <p className="mt-0.5 text-xs text-muted">{label}</p>
          </div>
        ))}
      </div>
      {(data.top_viewed.length > 0 || data.top_liked.length > 0) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {data.top_viewed.length > 0 && (
            <div className="wd-plate p-4">
              <p className="wd-eyebrow">Most viewed</p>
              {data.top_viewed.slice(0, 5).map((t) => (
                <p key={t.name} className="mt-1.5 flex justify-between text-sm">
                  <span className="truncate">{t.name}</span>
                  <span className="font-mono text-xs text-muted">{t.count}</span>
                </p>
              ))}
            </div>
          )}
          {data.top_liked.length > 0 && (
            <div className="wd-plate p-4">
              <p className="wd-eyebrow">Most liked</p>
              {data.top_liked.slice(0, 5).map((t) => (
                <p key={t.name} className="mt-1.5 flex justify-between text-sm">
                  <span className="truncate">{t.name}</span>
                  <span className="font-mono text-xs text-muted">{t.count}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

type AdminImport = {
  id: string
  username: string
  service: string
  status: string
  stats: Record<string, number>
  created_at: string
}

export function ImportsSection() {
  const { data } = useQuery({
    queryKey: ['admin-imports'],
    queryFn: () => api.get<AdminImport[]>('/api/admin/imports'),
  })
  if (!data || data.length === 0) return null
  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">Import jobs</h2>
      <div className="mt-4 flex flex-col gap-2">
        {data.map((row) => (
          <div
            key={row.id}
            className="wd-plate flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm"
          >
            <span className="font-mono text-xs text-muted">
              {new Date(row.created_at).toLocaleString()}
            </span>
            <span>{row.username}</span>
            <span className="font-mono text-xs text-muted">{row.service}</span>
            <span className="flex-1" />
            <span className="font-mono text-xs text-muted">
              {row.stats.imported ?? 0}/{row.stats.total ?? 0} imported
            </span>
            <span
              className={clsx(
                'font-mono text-[10px] uppercase',
                row.status === 'failed' ? 'text-danger' : 'text-muted',
              )}
            >
              {row.status}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
