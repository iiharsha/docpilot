import type { UIMessage } from 'ai'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import Conversation from '@/components/chat/Conversation'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { api, type ChatMessage } from '@/lib/api'

/** A stored row, in the shape `useChat` holds messages in. */
function toUIMessage(message: ChatMessage): UIMessage {
  return {
    id: message.id,
    role: message.role,
    parts: [{ type: 'text', text: message.content }],
  }
}

/** One thread: its stored history, then whatever is said next. */
export default function ChatThread() {
  const { threadId } = useParams<{ threadId: string }>()
  const location = useLocation()
  const navigate = useNavigate()

  const [history, setHistory] = useState<UIMessage[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Captured before the effect below clears it: router state lives in
  // `history.state` and survives a reload, which would otherwise re-ask the
  // question every time the page is refreshed.
  const [pendingText] = useState<string | undefined>(
    () => (location.state as { pendingText?: string } | null)?.pendingText,
  )

  useEffect(() => {
    if (pendingText) navigate(location.pathname, { replace: true, state: null })
  }, [pendingText, navigate, location.pathname])

  useEffect(() => {
    if (!threadId) return
    let active = true

    api
      .listMessages(threadId)
      .then((rows) => {
        if (active) setHistory(rows.map(toUIMessage))
      })
      .catch((cause: unknown) => {
        if (!active) return
        setError(cause instanceof Error ? cause.message : 'Could not load this chat')
      })

    return () => {
      active = false
    }
  }, [threadId])

  if (!threadId) return null

  if (error) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-8">
        <Alert variant="destructive">
          <AlertTitle>Could not load this chat</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    )
  }

  if (history === null) {
    return (
      <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm">
        Loading…
      </div>
    )
  }

  return (
    <Conversation
      threadId={threadId}
      initialMessages={history}
      pendingText={pendingText}
    />
  )
}
