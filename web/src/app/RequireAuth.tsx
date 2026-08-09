import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useMe } from './useMe'
import { ScreenLoader } from '../components/ScreenLoader'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { data: me, isLoading } = useMe()
  const location = useLocation()

  if (isLoading) return <ScreenLoader />
  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return children
}
