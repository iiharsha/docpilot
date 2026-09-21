import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '@/lib/auth-context'

/** Shown while the stored session is still being read. */
function Loading() {
  return (
    <div className="text-muted-foreground flex min-h-svh items-center justify-center text-sm">
      Loading…
    </div>
  )
}

/** Sends unauthenticated visitors to sign-in, remembering where they wanted. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const location = useLocation()

  if (loading) return <Loading />
  if (!session) {
    return (
      <Navigate to="/sign-in" replace state={{ from: location.pathname }} />
    )
  }
  return children
}

/** Keeps a signed-in analyst off the sign-in and sign-up forms. */
export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()

  if (loading) return <Loading />
  if (session) return <Navigate to="/" replace />
  return children
}
