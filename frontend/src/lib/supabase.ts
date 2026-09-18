import { createClient } from '@supabase/supabase-js'

import { env } from '@/lib/env'

/**
 * The browser Supabase client, used for authentication only.
 *
 * Anon key exclusively. The service-role key lives on the backend and must
 * never appear in this bundle. Product data is read through the FastAPI API,
 * not queried from here.
 */
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey)

/** The signed-in user's access token, or null when there is no session. */
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}
