import { Outlet, useLocation } from 'react-router-dom'

import ThreadSidebar from '@/components/chat/ThreadSidebar'
import { ThreadsProvider } from '@/lib/threads'

/** The signed-in shell: thread list on the left, the current chat on the right. */
export default function ChatLayout() {
  const location = useLocation()

  return (
    // Scoped to the chat routes, so the list is fetched once on entry and
    // shared by the sidebar and by whatever creates threads.
    <ThreadsProvider>
      <div className="flex h-svh">
        <ThreadSidebar />
        <main className="flex min-w-0 flex-1 flex-col">
          {/* Keyed on the path so switching threads remounts the page. React
              Router reuses an element when only a param changes, and `useChat`
              reads its initial messages once — so without this, opening a
              second thread would show the first one's conversation. */}
          <Outlet key={location.pathname} />
        </main>
      </div>
    </ThreadsProvider>
  )
}
