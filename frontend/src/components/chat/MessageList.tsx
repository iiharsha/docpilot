import type { UIMessage } from 'ai'

/** The readable body of a message. Only text parts carry one today. */
function messageText(message: UIMessage): string {
  return message.parts
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('')
}

type MessageListProps = {
  messages: UIMessage[]
  /** True while the last assistant message is still arriving. */
  streaming?: boolean
}

export default function MessageList({ messages, streaming }: MessageListProps) {
  return (
    <div className="flex flex-col gap-6">
      {messages.map((message, index) => {
        const isUser = message.role === 'user'
        // Only the last message can be the one still being written.
        const isStreaming = streaming && !isUser && index === messages.length - 1

        return (
          <div
            key={message.id}
            className={isUser ? 'flex justify-end' : 'flex justify-start'}
          >
            <div
              className={
                isUser
                  ? 'bg-secondary text-secondary-foreground max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap'
                  : 'max-w-[80%] text-sm leading-relaxed whitespace-pre-wrap'
              }
            >
              {messageText(message)}
              {isStreaming && (
                <span
                  aria-hidden
                  className="bg-foreground ml-0.5 inline-block h-4 w-[2px] animate-pulse align-text-bottom"
                />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
