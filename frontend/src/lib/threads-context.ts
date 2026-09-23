import { createContext, useContext } from 'react'

import type { Thread } from '@/lib/api'

export type ThreadsState = {
  /** The signed-in analyst's threads, most recent activity first. */
  threads: Thread[]
  /** True until the first load finishes. */
  loading: boolean
  /** Why the list could not be loaded, if it could not be. */
  error: string | null
  /**
   * Re-read the list. Called after a thread is created and after a turn
   * finishes, since the backend titles a thread from its first question and
   * reorders the list by last activity.
   */
  refresh: () => Promise<void>
}

export const ThreadsContext = createContext<ThreadsState | null>(null)

export function useThreads(): ThreadsState {
  const context = useContext(ThreadsContext)
  if (context === null) {
    throw new Error('useThreads must be used inside <ThreadsProvider>')
  }
  return context
}
