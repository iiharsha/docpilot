import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport, type UIMessage } from 'ai'
import { useEffect, useMemo, useRef } from 'react'

import Composer from '@/components/chat/Composer'
import MessageList from '@/components/chat/MessageList'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { ScrollArea } from '@/components/ui/scroll-area'
import { chatErrorMessage, chatStream } from '@/lib/api'
import { useThreads } from '@/lib/threads-context'

type ConversationProps = {
  threadId: string
  /** The thread's stored history. Read once, when `useChat` initialises. */
  initialMessages: UIMessage[]
  /** A question typed before the thread existed. Sent once, on mount. */
  pendingText?: string
}

/**
 * One thread's chat, once its history is loaded.
 *
 * Split from `ChatThread` because `useChat` reads `messages` only at init: the
 * history has to be in hand before this renders, and the alternative —
 * `setMessages` after a fetch — would race the pending first question and wipe
 * it. Remounted per thread by the `key` in `ChatLayout` for the same reason.
 */
export default function Conversation({
  threadId,
  initialMessages,
  pendingText,
}: ConversationProps) {
  const threads = useThreads()

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: chatStream.url,
        // `Resolvable`, so an async function is fine — it mints a fresh bearer
        // header per send rather than capturing a token that may have expired.
        headers: chatStream.headers,
        // The SDK's own body carries `id`/`messages`/`trigger`; `threadId` is
        // ours, and is what architecture.md specifies.
        body: { threadId },
      }),
    [threadId],
  )

  const { messages, sendMessage, status, error } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
    // The backend titles an untitled thread from its first question, and
    // bumps its `updated_at`. Neither shows in the sidebar until it re-reads.
    onFinish: () => void threads.refresh(),
  })

  // Deferred a tick, and marked sent only once it really is. `useChat` stops its
  // chat on unmount, which aborts a send still in flight — and StrictMode
  // unmounts every component once, synchronously, right after its first
  // effects run. Sent directly, the question was aborted there and the guard
  // then refused to resend it: the thread got no answer and showed no error.
  // Deferred, that unmount cancels the timer instead, and the remount's own
  // timer is the one that sends.
  const sentPending = useRef(false)
  useEffect(() => {
    if (sentPending.current || !pendingText) return
    const timer = setTimeout(() => {
      sentPending.current = true
      void sendMessage({ text: pendingText })
    })
    return () => clearTimeout(timer)
  }, [pendingText, sendMessage])

  // Follow the answer as it streams.
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages, status])

  const busy = status === 'submitted' || status === 'streaming'

  return (
    <>
      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-8">
          {/* Not while a first question is pending: it is sent from an effect,
              so the list is empty for one frame before it appears. */}
          {messages.length === 0 && !pendingText && (
            <p className="text-muted-foreground text-sm">
              No messages yet. Ask a question about the filings to get started.
            </p>
          )}

          <MessageList messages={messages} streaming={status === 'streaming'} />

          {status === 'submitted' && (
            <p className="text-muted-foreground animate-pulse text-sm">Thinking…</p>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertTitle>Could not answer that</AlertTitle>
              <AlertDescription>{chatErrorMessage(error)}</AlertDescription>
            </Alert>
          )}

          <div ref={bottom} />
        </div>
      </ScrollArea>

      <div className="border-t">
        <div className="mx-auto w-full max-w-3xl px-6 py-4">
          <Composer onSend={(text) => void sendMessage({ text })} disabled={busy} />
        </div>
      </div>
    </>
  )
}
