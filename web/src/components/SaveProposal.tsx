import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export type Proposal = {
  name: string
  titles: { tmdb_id: number; type: string; name: string }[]
}

type Result = { added: number; already_there: number; failed: number; list_name: string }

/* The assistant proposes a set; this is the press that saves it.
 *
 * Deliberately a button and not something automatic. The assistant can be
 * wrong, and an assistant that quietly writes to somebody's lists is not a
 * feature, it is something you have to undo. Nothing is written until this
 * is clicked, and the order the server proposed is the order it saves in.
 */
export function SaveProposal({ proposal }: { proposal: Proposal }) {
  const qc = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [failed, setFailed] = useState(false)

  async function save() {
    setSaving(true)
    setFailed(false)
    try {
      const out = await api.post<Result>('/api/lists/bulk', {
        name: proposal.name,
        titles: proposal.titles.map((t) => ({ tmdb_id: t.tmdb_id, type: t.type })),
      })
      setResult(out)
      qc.invalidateQueries({ queryKey: ['lists'] })
    } catch {
      setFailed(true)
    } finally {
      setSaving(false)
    }
  }

  if (result) {
    return (
      <p className="mt-4 text-sm text-muted">
        Saved {result.added} to{' '}
        <a href="/app/lists" className="text-ember hover:underline">
          {result.list_name}
        </a>
        {result.already_there > 0 ? `, ${result.already_there} already there` : ''}
        {result.failed > 0 ? `, ${result.failed} could not be found` : ''}.
      </p>
    )
  }

  return (
    <div className="wd-plate mt-4 flex flex-wrap items-center justify-between gap-3 p-3">
      <p className="min-w-0 text-sm">
        Save these {proposal.titles.length} as{' '}
        <span className="text-ember">{proposal.name}</span>, in order?
      </p>
      <div className="flex shrink-0 items-center gap-2">
        {failed && <span className="text-xs text-danger">That did not save. Try again?</span>}
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="rounded-[4px] border border-ember/50 px-3 py-1.5 text-xs text-ember transition-colors hover:bg-ember/10 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save the list'}
        </button>
      </div>
    </div>
  )
}
