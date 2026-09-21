import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { AuthShell } from '@/components/AuthShell'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { supabase } from '@/lib/supabase'

export default function SignIn() {
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Where the protected route sent us from, so sign-in returns there.
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)

    setError(null)
    setSubmitting(true)
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: String(form.get('email')),
      password: String(form.get('password')),
    })
    setSubmitting(false)

    if (signInError) {
      setError(signInError.message)
      return
    }

    void navigate(from, { replace: true })
  }

  return (
    <AuthShell>
      <Card>
        <CardHeader>
          <CardTitle>Sign in to Docpilot</CardTitle>
          <CardDescription>Use your BlueWood email address.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            {error && (
              <Alert variant="destructive">
                <AlertTitle>Could not sign in</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="analyst@bluewood.capital"
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </div>

            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>

          <p className="text-muted-foreground mt-4 text-sm">
            No account yet?{' '}
            <Link to="/sign-up" className="underline">
              Create one
            </Link>
          </p>
        </CardContent>
      </Card>
    </AuthShell>
  )
}
