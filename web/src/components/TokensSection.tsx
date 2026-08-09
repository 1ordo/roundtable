import { useState } from 'react'
import { motion } from 'motion/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

type TokenOut = {
  id: string
  name: string
  scopes: string[]
  last_used_at: string | null
  created_at: string
  revoked: boolean
}

type TokenList = {
  api_enabled_globally: boolean
  api_enabled_for_me: boolean
  tokens: TokenOut[]
}

export function TokensSection() {
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ['tokens'],
    queryFn: () => api.get<TokenList>('/api/tokens'),
  })
  const [name, setName] = useState('')
  const [scope, setScope] = useState<'read' | 'write'>('read')
  const [freshToken, setFreshToken] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => api.post<{ token: string }>('/api/tokens', { name, scope }),
    onSuccess: (result) => {
      setFreshToken(result.token)
      setName('')
      queryClient.invalidateQueries({ queryKey: ['tokens'] })
    },
  })
  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/api/tokens/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tokens'] }),
  })

  if (!data) return null

  const blocked = !data.api_enabled_globally || !data.api_enabled_for_me

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-semibold uppercase tracking-[0.02em]">API access</h2>
      <p className="mt-1 text-sm text-muted">
        Personal tokens for the browser extension, for scripts, and for connecting Claude
        through the MCP server at /api/mcp.
      </p>

      {/* The extension is the main reason anyone makes a token, so it says
          so here rather than leaving people to find out elsewhere. */}
      <div className="wd-plate mt-4 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm">The browser extension</p>
            <p className="mt-1 max-w-lg text-xs text-muted">
              Logs what you watch on Netflix, Prime, Shahid, OSN and the rest, offers to
              import your saved list, and asks what you thought when the credits roll. It
              needs a token with write access from below.
            </p>
          </div>
          <a
            href="https://github.com/1ordo/watchpile/tree/main/extension#readme"
            target="_blank"
            rel="noreferrer noopener"
            className="shrink-0 rounded-[4px] border border-line px-3.5 py-2 text-sm text-muted transition-colors hover:border-ember hover:text-ember"
          >
            How to install it
          </a>
        </div>
      </div>

      {blocked && (
        <p className="wd-plate mt-3 px-4 py-3 text-sm text-muted">
          {!data.api_enabled_globally
            ? 'API access is switched off for everyone. An admin can enable it under Admin, feature flags.'
            : 'API access is not enabled for your account yet. Ask your admin to switch it on.'}
        </p>
      )}

      {!blocked && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Token name, e.g. claude"
            className="rounded-[4px] border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ember focus:outline-none"
          />
          <div className="flex rounded-md border border-line p-1">
            {(['read', 'write'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setScope(s)}
                className={
                  scope === s
                    ? 'rounded-[4px] bg-ember px-3 py-1 text-xs text-ink'
                    : 'rounded-[4px] px-3 py-1 text-xs text-muted hover:text-fg'
                }
              >
                {s === 'read' ? 'Read only' : 'Read and write'}
              </button>
            ))}
          </div>
          <button
            onClick={() => create.mutate()}
            disabled={!name.trim() || create.isPending}
            className="rounded-[4px] bg-ember px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ember/90 disabled:opacity-40"
          >
            Create token
          </button>
        </div>
      )}

      {freshToken && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 rounded-md border border-ember/50 bg-ember/10 p-4"
        >
          <p className="text-sm">Copy it now; it is shown only once.</p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 overflow-x-auto rounded bg-ink px-3 py-2 font-mono text-xs">
              {freshToken}
            </code>
            <button
              onClick={() => navigator.clipboard.writeText(freshToken)}
              className="rounded-[4px] border border-line px-3 py-2 text-xs transition-colors hover:border-ember hover:text-ember"
            >
              Copy
            </button>
            <button
              onClick={() => setFreshToken(null)}
              className="text-xs text-muted hover:text-fg"
            >
              Done
            </button>
          </div>
        </motion.div>
      )}

      {data.tokens.length > 0 && (
        <div className="mt-4 flex flex-col gap-2">
          {data.tokens.map((token) => (
            <div
              key={token.id}
              className="wd-plate flex items-center gap-3 px-4 py-2.5"
            >
              <span className="flex-1 truncate text-sm">{token.name}</span>
              <span className="font-mono text-[10px] text-muted uppercase">
                {token.scopes.includes('write') ? 'read+write' : 'read'}
              </span>
              <span className="font-mono text-[10px] text-muted">
                {token.revoked
                  ? 'revoked'
                  : token.last_used_at
                    ? `used ${new Date(token.last_used_at).toLocaleDateString()}`
                    : 'never used'}
              </span>
              {!token.revoked && (
                <button
                  onClick={() => revoke.mutate(token.id)}
                  className="text-xs text-muted transition-colors hover:text-danger"
                >
                  Revoke
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
