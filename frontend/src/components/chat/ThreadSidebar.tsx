import { LogOut, MessageSquarePlus } from 'lucide-react'
import { NavLink, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useAuth } from '@/lib/auth-context'
import { supabase } from '@/lib/supabase'
import { useThreads } from '@/lib/threads-context'

/**
 * Past conversations, plus the way into a new one.
 *
 * A plain `<aside>` rather than shadcn's `sidebar` block: that block is a
 * navigation system (mobile sheet, collapsible rail, cookie-persisted state,
 * keyboard shortcut) and this is a list with a button above it. The rule about
 * not hand-rolling shadcn primitives is about primitives — `scroll-area` and
 * `button` below are the primitives here.
 */
export default function ThreadSidebar() {
  const { threads, loading, error } = useThreads()
  const { session } = useAuth()
  const navigate = useNavigate()

  return (
    <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border flex w-64 shrink-0 flex-col border-r">
      <div className="p-3">
        <Button
          variant="outline"
          className="w-full justify-start"
          // Navigation only — the thread itself is created by the first
          // message, so an abandoned click leaves nothing behind.
          onClick={() => navigate('/chats')}
        >
          <MessageSquarePlus data-icon="inline-start" />
          New chat
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <nav className="flex flex-col gap-0.5 px-3 pb-3">
          {loading && <p className="text-muted-foreground px-2 py-1 text-xs">Loading…</p>}

          {error && <p className="text-destructive px-2 py-1 text-xs">{error}</p>}

          {!loading && !error && threads.length === 0 && (
            <p className="text-muted-foreground px-2 py-1 text-xs">No chats yet.</p>
          )}

          {threads.map((thread) => (
            <NavLink
              key={thread.id}
              to={`/chats/${thread.id}`}
              className={({ isActive }) =>
                `truncate rounded-lg px-2 py-1.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'hover:bg-sidebar-accent/60'
                }`
              }
            >
              {/* Untitled until the first answer is persisted. */}
              {thread.title ?? 'New chat'}
            </NavLink>
          ))}
        </nav>
      </ScrollArea>

      <div className="border-sidebar-border flex items-center justify-between gap-2 border-t p-3">
        <span className="text-muted-foreground truncate text-xs">
          {session?.user.email}
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => void supabase.auth.signOut()}
          aria-label="Sign out"
        >
          <LogOut />
        </Button>
      </div>
    </aside>
  )
}
