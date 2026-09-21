"""Persistence for `public.users`.

Supabase owns `auth.users`; this is our application row. `chat_threads.user_id`
has a foreign key to it, so a thread cannot be created until the row exists.

Written with the service-role client: RLS has no insert policy on `users`
(migration 0001 keeps writes backend-only), and on a user's very first request
there is no row to be scoped to yet.
"""

import uuid

from supabase import AsyncClient


async def upsert_user(client: AsyncClient, user_id: uuid.UUID, email: str) -> None:
    """Create or refresh the caller's row, keyed by their `auth.users` id.

    Only the columns we own are sent, so `full_name` survives a later sign-in.
    """
    await (
        client.table("users")
        .upsert({"id": str(user_id), "email": email}, on_conflict="id")
        .execute()
    )
