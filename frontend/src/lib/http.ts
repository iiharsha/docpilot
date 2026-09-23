import { env } from '@/lib/env'
import { getAccessToken } from '@/lib/supabase'

const DEFAULT_TIMEOUT_MS = 30_000

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export type RequestOptions = {
  method?: HttpMethod
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
  timeoutMs?: number
}

/**
 * A failed API call.
 *
 * `isNetworkError` separates "no answer ever arrived" — offline, DNS failure,
 * CORS rejection, timeout — from "the backend answered with an error status".
 * The first is worth retrying and usually means the deployment is wrong; the
 * second is the documented error contract and carries a real status.
 *
 * `detail` keeps the parsed error body. FastAPI's 422 puts an array of field
 * errors there, which no single message can carry.
 */
export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown
  readonly isNetworkError: boolean

  constructor(
    message: string,
    options: { status: number; detail?: unknown; isNetworkError?: boolean },
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status
    this.detail = options.detail
    this.isNetworkError = options.isNetworkError ?? false
  }
}

/** Bearer header for the current session, or empty when signed out. */
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function buildUrl(path: string): string {
  return path.startsWith('/')
    ? `${env.apiBaseUrl}${path}`
    : `${env.apiBaseUrl}/${path}`
}

function isJson(response: Response): boolean {
  return (response.headers.get('content-type') ?? '').includes('application/json')
}

/** Parse whatever the server sent, without assuming it is JSON. */
async function readBody(response: Response): Promise<unknown> {
  try {
    if (isJson(response)) return await response.json()
    const text = await response.text()
    return text.length > 0 ? text : null
  } catch {
    return null
  }
}

export function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim() !== '') return detail

  // FastAPI reports failures as {"detail": ...}.
  if (detail !== null && typeof detail === 'object' && 'detail' in detail) {
    const inner = (detail as { detail: unknown }).detail
    if (typeof inner === 'string' && inner.trim() !== '') return inner
  }

  return fallback
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = 'GET',
    body,
    headers = {},
    signal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  } = options

  // Serialized before the fetch below: a circular body is a caller bug, and
  // must not be swallowed by that catch and relabelled a network error.
  const payload = body === undefined ? undefined : JSON.stringify(body)

  const requestHeaders = new Headers(headers)
  for (const [key, value] of Object.entries(await authHeaders())) {
    if (!requestHeaders.has(key)) requestHeaders.set(key, value)
  }
  if (payload !== undefined && !requestHeaders.has('Content-Type')) {
    requestHeaders.set('Content-Type', 'application/json')
  }

  const timeout = AbortSignal.timeout(timeoutMs)
  const abortSignal = signal ? AbortSignal.any([signal, timeout]) : timeout

  let response: Response
  try {
    response = await fetch(buildUrl(path), {
      method,
      headers: requestHeaders,
      body: payload,
      signal: abortSignal,
    })
  } catch (cause) {
    // A caller cancelling on purpose is not an error worth relabelling.
    if (signal?.aborted) throw cause

    // `fetch` only rejects when no response arrived at all.
    throw new ApiError(
      timeout.aborted
        ? `Request timed out after ${timeoutMs}ms`
        : 'Could not reach the server',
      { status: 0, isNetworkError: true },
    )
  }

  if (!response.ok) {
    const structured = isJson(response)
    const detail = await readBody(response)
    const fallback = response.statusText || `Request failed with ${response.status}`
    // Only a JSON body yields a message. A proxy's HTML error page is kept on
    // `detail` for logs, but must never be rendered at a user.
    throw new ApiError(structured ? errorMessage(detail, fallback) : fallback, {
      status: response.status,
      detail,
    })
  }

  // 204, or any success the backend did not send as JSON.
  if (response.status === 204 || !isJson(response)) return undefined as T
  return (await response.json()) as T
}
