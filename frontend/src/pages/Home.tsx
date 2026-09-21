import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-context'
import { supabase } from '@/lib/supabase'

/**
 * Placeholder landing page for a signed-in analyst.
 *
 * The thread sidebar and chat view replace this; it exists so the protected
 * route has a destination and the auth flow can be walked end to end.
 */
export default function Home() {
  const { session } = useAuth()

  return (
    <main className="mx-auto flex min-h-svh max-w-2xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Docpilot</h1>
          <p className="text-muted-foreground text-sm">
            Signed in as {session?.user.email}
          </p>
        </div>
        <Button variant="outline" onClick={() => void supabase.auth.signOut()}>
          Sign out
        </Button>
      </header>

      <p className="text-muted-foreground text-sm">
        Chat view coming next.
      </p>
    </main>
  )
}
