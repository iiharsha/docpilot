import { env } from '@/lib/env'
import { authHeaders, request, type RequestOptions } from '@/lib/http'

/**
 * Product-level calls against the FastAPI backend.
 *
 * Field names are camelCase on the wire, matching the `threadId` in
 * architecture.md's `/chat/stream` request body. The backend serialises its
 * snake_case models to this shape.
 */

export type Thread = {
  id: string
  title: string | null
  createdAt: string
  updatedAt: string
}

/**
 * One cited passage. Shaped from the `message_citations` and `source_documents`
 * columns, and carrying everything the brief requires a citation to show:
 * company, filing, date, and where in the document it came from.
 */
export type Citation = {
  marker: number
  excerpt: string
  section: string | null
  page: number | null
  ticker: string
  companyName: string
  formType: string
  filingDate: string
  fiscalYear: number
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sequence: number
  createdAt: string
  citations: Citation[]
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),

  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),

  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),

  /** The signed-in user's threads, newest activity first. */
  listThreads: () => request<Thread[]>('/threads'),

  createThread: (title?: string) =>
    request<Thread>('/threads', { method: 'POST', body: { title } }),

  renameThread: (threadId: string, title: string) =>
    request<Thread>(`/threads/${threadId}`, { method: 'PATCH', body: { title } }),

  deleteThread: (threadId: string) =>
    request<void>(`/threads/${threadId}`, { method: 'DELETE' }),

  /** Stored history for a thread, oldest first, with citations attached. */
  listMessages: (threadId: string) =>
    request<ChatMessage[]>(`/threads/${threadId}/messages`),
}

/**
 * Wiring for the AI SDK chat transport.
 *
 * The SDK owns the streaming request itself, so it needs the URL and a way to
 * mint a fresh bearer header per send rather than going through `request`.
 */
export const chatStream = {
  url: `${env.apiBaseUrl}/chat/stream`,
  headers: authHeaders,
}
