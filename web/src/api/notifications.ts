import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

export type NotificationOut = {
  id: string
  kind: string
  message: string
  payload: Record<string, unknown>
  read: boolean
  created_at: string
  title_tmdb_id: number | null
  title_type: string | null
  title_poster: string | null
  link: string | null
}

export type Inbox = { unread: number; notifications: NotificationOut[] }

export function useInbox() {
  return useQuery({
    queryKey: ['inbox'],
    queryFn: () => api.get<Inbox>('/api/notifications'),
    refetchInterval: 60_000,
  })
}

export function useMarkRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/notifications/${id}/read`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['inbox'] }),
  })
}

export function useMarkAllRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/api/notifications/read-all'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['inbox'] }),
  })
}
