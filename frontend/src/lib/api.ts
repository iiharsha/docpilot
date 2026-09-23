import { APICallError } from 'ai'

import { env } from '@/lib/env'
import { authHeaders, errorMessage, request, type RequestOptions } from '@/lib/http'

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
  /** Text, not a number: filings label pages "F-12" as often as "42". */
  page: string | null
  ticker: string
  companyName: string
  formType: string
  filingDate: string
  /**
   * Nullable: it comes from `source_documents`, and
   * `message_citations.document_id` is `ON DELETE SET NULL` by design.
   */
  fiscalYear: number | null
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

/**
 * What to tell the analyst when a chat turn fails.
 *
 * Bypassing `request` also bypasses its rule that only a JSON body becomes a
 * message. On an HTTP error the SDK puts the raw response body in `message` —
 * FastAPI's JSON, or a proxy's HTML error page — so it gets the same treatment
 * here. An in-band `error` part arrives as a plain `Error` whose text the
 * backend wrote for a person, and is shown as it is.
 */
export function chatErrorMessage(error: Error): string {
  if (APICallError.isInstance(error)) {
    const fallback = `Request failed with ${error.statusCode ?? 'an error'}`
    try {
      return errorMessage(JSON.parse(error.responseBody ?? ''), fallback)
    } catch {
      return fallback
    }
  }
  // The SDK's own test for a request that never got an answer.
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) {
    return 'Could not reach the server'
  }
  return error.message
}
