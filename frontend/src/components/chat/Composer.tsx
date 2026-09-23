import { SendHorizontal } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

type ComposerProps = {
  onSend: (text: string) => void
  /** False while a turn is in flight, so one question cannot be asked twice. */
  disabled?: boolean
  placeholder?: string
}

/** The question box. Enter sends, Shift+Enter starts a new line. */
export default function Composer({ onSend, disabled, placeholder }: ComposerProps) {
  const [text, setText] = useState('')
  const trimmed = text.trim()

  function submit(event: FormEvent) {
    event.preventDefault()
    if (disabled || trimmed === '') return
    onSend(trimmed)
    setText('')
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // `isComposing` guards an IME: Enter there is accepting a candidate word,
    // not sending the message.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      submit(event)
    }
  }

  return (
    <form onSubmit={submit} className="flex items-end gap-2">
      <Textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder ?? 'Ask about the filings…'}
        rows={1}
        // `field-sizing-content` on the primitive grows the box with the text;
        // the cap keeps a pasted paragraph from swallowing the conversation.
        className="max-h-48 min-h-11 resize-none"
        aria-label="Message"
      />
      <Button
        type="submit"
        size="icon-lg"
        disabled={disabled || trimmed === ''}
        aria-label="Send"
      >
        <SendHorizontal />
      </Button>
    </form>
  )
}
