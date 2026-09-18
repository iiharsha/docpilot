/**
 * The only module that reads `import.meta.env`.
 *
 * Validation runs at import, so a missing variable stops the app at boot with
 * one message naming everything that is absent — rather than surfacing later as
 * an undefined URL in a fetch call.
 */

type EnvKey = 'VITE_API_BASE_URL' | 'VITE_SUPABASE_URL' | 'VITE_SUPABASE_ANON_KEY'

const REQUIRED: EnvKey[] = [
  'VITE_API_BASE_URL',
  'VITE_SUPABASE_URL',
  'VITE_SUPABASE_ANON_KEY',
]

function readRequired(): Record<EnvKey, string> {
  const source = import.meta.env as Record<string, string | undefined>
  const values = {} as Record<EnvKey, string>
  const missing: EnvKey[] = []

  for (const key of REQUIRED) {
    const value = source[key]?.trim()
    if (value) {
      values[key] = value
    } else {
      missing.push(key)
    }
  }

  if (missing.length > 0) {
    throw new Error(
      `Missing frontend environment variables: ${missing.join(', ')}. ` +
        'Copy frontend/.env.example to frontend/.env and fill in the values.',
    )
  }

  return values
}

const values = readRequired()

export const env = {
  // Trailing slashes stripped so callers can join paths without doubling them.
  apiBaseUrl: values.VITE_API_BASE_URL.replace(/\/+$/, ''),
  supabaseUrl: values.VITE_SUPABASE_URL.replace(/\/+$/, ''),
  supabaseAnonKey: values.VITE_SUPABASE_ANON_KEY,
} as const
