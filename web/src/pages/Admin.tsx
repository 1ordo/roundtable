import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { api } from '../api/client'
import { useAISettings, useAIStatus, type AISettings } from '../api/ai'
import {
  ActivitySection,
  AuditSection,
  FlagsSection,
  ImportsSection,
  UsersSection,
} from '../components/AdminSections'
import { AuthSettingsSection } from '../components/AuthSettingsSection'

type Quota = {
  today: Record<string, number>
  omdb_daily_budget: number
  tmdb_configured: boolean
  omdb_configured: boolean
  last_30_days: { day: string; source: string; count: number }[]
}

function useQuota() {
  return useQuery({
    queryKey: ['admin-quota'],
    queryFn: () => api.get<Quota>('/api/admin/quota'),
  })
}

function QuotaCard({
  label,
  used,
  budget,
  configured,
}: {
  label: string
  used: number
  budget: number | null
  configured: boolean
}) {
  const percent = budget ? Math.min(100, (used / budget) * 100) : 0
  return (
    <div className="wd-plate p-5">
      <div className="flex items-baseline justify-between">
        <p className="font-display text-lg font-semibold uppercase">{label}</p>
        <p className="font-mono text-xs text-muted">
          {configured ? 'key set' : 'no key'}
        </p>
      </div>
      <p className="mt-3 font-mono text-2xl">
        {used}
        {budget && <span className="text-sm text-muted"> / {budget} today</span>}
        {!budget && <span className="text-sm text-muted"> requests today</span>}
      </p>
      {budget && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-panel-2">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${percent}%` }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className={clsx('h-full rounded-full', percent > 85 ? 'bg-danger' : 'bg-ember')}
          />
        </div>
      )}
    </div>
  )
}

function AISettingsForm() {
  const { data: saved } = useAISettings()
  const { data: status } = useAIStatus()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<AISettings | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    if (saved && form === null) setForm(saved)
  }, [saved, form])

  const save = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.put<AISettings>('/api/admin/settings/ai', payload),
    onSuccess: (data) => {
      queryClient.setQueryData(['ai-settings'], data)
      queryClient.invalidateQueries({ queryKey: ['ai-status'] })
      setForm(data)
      setApiKey('')
      setSavedFlash(true)
      setTimeout(() => setSavedFlash(false), 2000)
    },
  })

  if (!form) return null

  return (
    <div className="wd-plate p-5">
      <div className="flex items-center justify-between">
        <p className="font-display text-lg font-semibold uppercase">AI settings</p>
        {status && (
          <p className="font-mono text-xs text-muted">
            {status.embedded_titles} titles embedded
          </p>
        )}
      </div>
      <p className="mt-1 text-sm text-muted">
        Points at any OpenAI-compatible server. The app works fully with this off; AI adds
        the for-you rows, ask-search, and vibe tags.
      </p>

      <label className="mt-5 flex cursor-pointer items-center gap-3">
        <button
          role="switch"
          aria-checked={form.enabled}
          onClick={() => setForm({ ...form, enabled: !form.enabled })}
          className={clsx(
            'relative h-6 w-11 rounded-full transition-colors',
            form.enabled ? 'bg-ember' : 'bg-panel-2',
          )}
        >
          <motion.span
            layout
            transition={{ type: 'spring', stiffness: 600, damping: 40 }}
            className={clsx(
              'absolute top-0.5 h-5 w-5 rounded-full bg-ink',
              form.enabled ? 'right-0.5' : 'left-0.5',
            )}
          />
        </button>
        <span className="text-sm">AI features {form.enabled ? 'on' : 'off'}</span>
      </label>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">Base URL</span>
          <input
            value={form.base_url}
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            className="w-full rounded-[4px] border border-line bg-ink px-3 py-2 font-mono text-xs focus:border-ember focus:outline-none"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">
            API key {form.has_api_key ? '(set, leave blank to keep)' : '(optional)'}
          </span>
          <input
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            type="password"
            autoComplete="off"
            placeholder={form.has_api_key ? 'unchanged' : 'not needed for LM Studio'}
            className="w-full rounded-[4px] border border-line bg-ink px-3 py-2 font-mono text-xs focus:border-ember focus:outline-none"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">Chat model</span>
          <input
            value={form.chat_model}
            onChange={(e) => setForm({ ...form, chat_model: e.target.value })}
            className="w-full rounded-[4px] border border-line bg-ink px-3 py-2 font-mono text-xs focus:border-ember focus:outline-none"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted">Embedding model</span>
          <input
            value={form.embed_model}
            onChange={(e) => setForm({ ...form, embed_model: e.target.value })}
            className="w-full rounded-[4px] border border-line bg-ink px-3 py-2 font-mono text-xs focus:border-ember focus:outline-none"
          />
        </label>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <button
          onClick={() =>
            save.mutate({
              enabled: form.enabled,
              base_url: form.base_url,
              chat_model: form.chat_model,
              embed_model: form.embed_model,
              ...(apiKey ? { api_key: apiKey } : {}),
            })
          }
          disabled={save.isPending}
          className="rounded-[4px] bg-ember px-5 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-50"
        >
          Save AI settings
        </button>
        {savedFlash && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-sm text-nitrate"
          >
            Saved
          </motion.span>
        )}
        {save.error && <span className="text-sm text-danger">{save.error.message}</span>}
      </div>
    </div>
  )
}

export function Admin() {
  const { data: quota } = useQuota()

  return (
    <div className="max-w-3xl">
      <header className="mb-8">
        <p className="wd-eyebrow">The booth</p>
        <h1 className="mt-1 font-display text-5xl font-semibold uppercase tracking-[0.01em]">
          Admin
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted">
          API budgets, AI configuration, people, feature flags, and the audit log.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <QuotaCard
          label="TMDB"
          used={quota?.today.tmdb ?? 0}
          budget={null}
          configured={quota?.tmdb_configured ?? false}
        />
        <QuotaCard
          label="OMDb"
          used={quota?.today.omdb ?? 0}
          budget={quota?.omdb_daily_budget ?? 1000}
          configured={quota?.omdb_configured ?? false}
        />
      </div>

      <div className="mt-6">
        <AISettingsForm />
      </div>

      <AuthSettingsSection />
      <ActivitySection />
      <UsersSection />
      <FlagsSection />
      <ImportsSection />
      <AuditSection />
    </div>
  )
}
