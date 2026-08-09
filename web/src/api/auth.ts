import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

export type AuthMethods = {
  oidc: boolean
  password: boolean
  registration_open: boolean
}

export type AuthSettings = {
  oidc_enabled: boolean
  password_enabled: boolean
  registration_open: boolean
  oidc_configured: boolean
}

export function useAuthMethods() {
  return useQuery({
    queryKey: ['auth-methods'],
    queryFn: () => api.get<AuthMethods>('/api/auth/methods'),
    retry: false,
    staleTime: 60_000,
  })
}

export function usePasswordLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { username: string; password: string }) =>
      api.post<{ username: string; role: string }>('/api/auth/password/login', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useRegister() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { username: string; password: string; email?: string }) =>
      api.post<{ username: string; role: string }>('/api/auth/password/register', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (input: { current_password?: string; new_password: string }) =>
      api.post('/api/auth/password/change', input),
  })
}

export function useAuthSettings() {
  return useQuery({
    queryKey: ['auth-settings'],
    queryFn: () => api.get<AuthSettings>('/api/admin/settings/auth'),
  })
}

export function useUpdateAuthSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      oidc_enabled: boolean
      password_enabled: boolean
      registration_open: boolean
    }) => api.put<AuthSettings>('/api/admin/settings/auth', body),
    onSuccess: (data) => {
      queryClient.setQueryData(['auth-settings'], data)
      queryClient.invalidateQueries({ queryKey: ['auth-methods'] })
    },
  })
}
