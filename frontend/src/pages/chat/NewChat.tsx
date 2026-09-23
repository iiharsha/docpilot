import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import Composer from '@/components/chat/Composer'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { api } from '@/lib/api'
import { useThreads } from '@/lib/threads-context'

/**
 * A chat that has no thread yet.
 *
 * The thread is created by the first question rather than by the "New chat"
 * button, so clicking that button and changing your mind leaves no empty row in
 * the sidebar. The question travels to the new route as router state; the
 * thread's own page sends it.
 */
export default function NewChat() {
  const navigate = useNavigate()
  const threads = useThreads()
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function start(text: string) {
    setCreating(true)
    setError(null)
    try {
      // Untitled: the backend names it from this first question.
      const thread = await api.createThread()
      await threads.refresh()
      navigate(`/chats/${thread.id}`, {
        replace: true,
        state: { pendingText: text },
      })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start a new chat')
      setCreating(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-6 py-8">
      <div className="space-y-1.5">
        <h1 className="text-2xl font-semibold">Ask about the filings</h1>
        <p className="text-muted-foreground text-sm">
          Questions are answered from the 10-K corpus, with the passages they came from.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Could not start a new chat</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Composer onSend={(text) => void start(text)} disabled={creating} />
    </div>
  )
}
