"""Supabase client construction.

Two clients, kept deliberately separate:

- `create_user_client` acts as the signed-in user. It sends the anon key as
  `apiKey` and the user's JWT as `Authorization`, so Postgres resolves
  `auth.uid()` and the RLS policies from migration 0001 apply. Build one per
  request and never share it between users.
- `create_service_client` uses the service-role key, which bypasses RLS
  entirely. Built once at startup and kept on `app.state.supabase_service`.
  It is only for work a user's own token cannot do, such as the `users` upsert
  on first sign-in. Ingestion does not use it: replacing a filing's chunks has
  to be one transaction, so `ingest/store.py` writes over `DATABASE_URL`.

This module is the only place the service-role key is read. It must never be
sent to the browser, written to a log, or accepted as a user access token.
"""

from supabase import AsyncClient, AsyncClientOptions, create_async_client

from app.config import settings


def _server_options(access_token: str | None = None) -> AsyncClientOptions:
    """Options shared by both clients.

    `auto_refresh_token` and `persist_session` default to True for browser use.
    On the server there is no session to keep, and the refresh task would run
    for the life of the process with nothing to refresh.
    """
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    return AsyncClientOptions(
        headers=headers,
        auto_refresh_token=False,
        persist_session=False,
    )


async def create_user_client(access_token: str) -> AsyncClient:
    """Build a client that acts as the user the token belongs to."""
    # `access_token` arrives from an Authorization header, so it is untrusted
    # input. A request carrying the service-role key would otherwise get back a
    # client with full RLS bypass instead of one scoped to a single user.
    if access_token == settings.supabase_service_role_key:
        raise ValueError(
            "refusing to build a user-scoped client from the service-role key"
        )

    return await create_async_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=_server_options(access_token),
    )


async def create_service_client() -> AsyncClient:
    """Build the privileged client. Backend only — it is not subject to RLS."""
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=_server_options(),
    )
