import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, postForm } from './client'

export type ImportCandidate = {
  tmdb_id: number
  type: 'movie' | 'tv'
  name: string
  year: number | null
  poster_path: string | null
}

export type ReviewEntry = {
  index: number
  raw: string
  name: string
  watched_at: string | null
  candidates: ImportCandidate[]
  resolved: boolean
}

export type ImportBatch = {
  id: string
  service: string
  target: string
  filename: string | null
  status: 'pending' | 'processing' | 'review' | 'done' | 'failed'
  error: string | null
  stats: Record<string, number>
  pending_review: number
  created_at: string
}

export type ImportBatchDetail = ImportBatch & { review_queue: ReviewEntry[] }

export function useImports() {
  return useQuery({
    queryKey: ['imports'],
    queryFn: () => api.get<ImportBatch[]>('/api/imports'),
    refetchInterval: (query) =>
      query.state.data?.some((b) => b.status === 'pending' || b.status === 'processing')
        ? 2000
        : false,
  })
}

export function useImportDetail(batchId: string | undefined) {
  return useQuery({
    queryKey: ['import', batchId],
    queryFn: () => api.get<ImportBatchDetail>(`/api/imports/${batchId}`),
    enabled: !!batchId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'processing' ? 2000 : false
    },
  })
}

export function useCreateImport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { service: string; target?: string; file?: File; payload?: string }) => {
      const form = new FormData()
      form.append('service', input.service)
      if (input.target) form.append('target', input.target)
      if (input.file) form.append('file', input.file)
      if (input.payload) form.append('payload', input.payload)
      return postForm<ImportBatch>('/api/imports', form)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['imports'] }),
  })
}

export function useResolveImport(batchId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { index: number; tmdb_id: number; type: string }) =>
      api.post<ImportBatch>(`/api/imports/${batchId}/resolve`, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['import', batchId] })
      queryClient.invalidateQueries({ queryKey: ['imports'] })
      queryClient.invalidateQueries({ queryKey: ['history'] })
      queryClient.invalidateQueries({ queryKey: ['lists'] })
    },
  })
}

export function useDismissImport(batchId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { index: number }) =>
      api.post<ImportBatch>(`/api/imports/${batchId}/dismiss`, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['import', batchId] })
      queryClient.invalidateQueries({ queryKey: ['imports'] })
    },
  })
}
