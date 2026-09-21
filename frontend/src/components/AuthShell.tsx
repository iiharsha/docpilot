import type { ReactNode } from 'react'

/** Centred column for the sign-in and sign-up cards. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <div className="w-full max-w-sm">{children}</div>
    </main>
  )
}
