/**
 * The only module that reads `import.meta.env`.
 *
 * Validation runs at import, so a missing variable stops the app at boot with
 * one message naming everything that is absent — rather than surfacing later as
 * an undefined URL in a fetch call.
 */

const raw = {
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  VITE_SUPABASE_URL: import.meta.env.VITE_SUPABASE_URL,
  VITE_SUPABASE_ANON_KEY: import.meta.env.VITE_SUPABASE_ANON_KEY,
}

const missing = Object.entries(raw)
  .filter(([, v]) => !v?.trim())
  .map(([k]) => k)

if (missing.length) {
  throw new Error(
    `Missing frontend environment variables: ${missing.join(', ')}. ` +
      'Copy frontend/.env.example to frontend/.env and fill in the values.',
  )
}

const stripSlash = (s: string) => s.trim().replace(/\/+$/, '')

export const env = {
  apiBaseUrl: stripSlash(raw.VITE_API_BASE_URL!),
  supabaseUrl: stripSlash(raw.VITE_SUPABASE_URL!),
  supabaseAnonKey: raw.VITE_SUPABASE_ANON_KEY!.trim(),
} as const
