import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, type Thread } from '@/lib/api'
import { ThreadsContext } from '@/lib/threads-context'

/**
 * The thread list, shared by the sidebar and by whatever is creating threads.
 *
 * `useState` + `useContext`, per `frontend/.rules`: one list of at most a few
 * hundred rows, read in two places, is not a reason for a state library.
 */
export function ThreadsProvider({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<Thread[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // A promise chain rather than async/await so the state updates land in a
  // callback, which is the shape `react-hooks/set-state-in-effect` asks for —
  // and the same shape `auth.tsx` uses for its session lookup.
  const refresh = useCallback(
    () =>
      api.listThreads().then(
        (rows) => {
          setThreads(rows)
          setError(null)
          setLoading(false)
        },
        (cause: unknown) => {
          setError(
            cause instanceof Error ? cause.message : 'Could not load your chats',
          )
          setLoading(false)
        },
      ),
    [],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(
    () => ({ threads, loading, error, refresh }),
    [threads, loading, error, refresh],
  )

  return <ThreadsContext.Provider value={value}>{children}</ThreadsContext.Provider>
}
