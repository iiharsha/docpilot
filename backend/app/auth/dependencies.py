"""Request authentication.

Every protected route depends on `get_current_user`, which verifies the bearer
token against Supabase Auth before the request reaches retrieval or the LLM.
An unauthenticated request costs one call to Supabase and nothing else.
"""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import httpx
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError, AuthError

from app.database.supabase import create_user_client
from app.database.users import upsert_user
from app.dependencies import ServiceClient

log = structlog.get_logger(__name__)

# `auto_error` already answers a missing or non-Bearer Authorization with 401
# and a WWW-Authenticate header, which is the contract in architecture.md.
bearer_scheme = HTTPBearer()


class AuthenticatedUser(BaseModel):
    """The verified caller — only what routes and persistence actually need."""

    # Frozen: the authenticated identity must not change mid-request.
    model_config = ConfigDict(frozen=True)

    id: UUID
    email: str


def _unauthorized(detail: str) -> HTTPException:
    # RFC 7235: a 401 has to say how to authenticate.
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> str:
    return credentials.credentials


async def get_user_client(
    access_token: Annotated[str, Depends(get_access_token)],
) -> AsyncIterator[AsyncClient]:
    """The caller's Supabase client, so RLS scopes every query to them.

    Not proof of authentication by itself — routes depend on `get_current_user`
    for that. FastAPI caches dependencies per request, so the two share one
    client rather than opening a second connection pool.
    """
    client = await create_user_client(access_token)
    try:
        yield client
    finally:
        # One client, two lazily-built httpx pools: `auth` opens on the token
        # check, `postgrest` on the first query. Both have to be closed or the
        # sockets outlive the request. Closing an unused one costs nothing —
        # constructing an httpx client opens no connection.
        await client.auth.close()
        await client.postgrest.aclose()


async def get_current_user(
    access_token: Annotated[str, Depends(get_access_token)],
    client: Annotated[AsyncClient, Depends(get_user_client)],
    service_client: ServiceClient,
) -> AuthenticatedUser:
    """Verify the bearer token against Supabase Auth and identify the caller."""
    try:
        response = await client.auth.get_user(access_token)
    except AuthApiError as exc:
        # Supabase rejected the token: expired, malformed, or revoked.
        raise _unauthorized("Invalid or expired token") from exc
    except (AuthError, httpx.HTTPError) as exc:
        # Supabase is unreachable or erroring, which is not the caller's fault.
        # `get_user` only wraps HTTP *status* errors, so a connection failure
        # arrives here as a raw httpx error and would otherwise surface as 500.
        log.warning("supabase_auth_unavailable", error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Authentication service unavailable"
        ) from exc

    if response is None or response.user is None:
        raise _unauthorized("Invalid or expired token")

    # Sign-in is email-only, so a user without an address cannot be an analyst.
    if not response.user.email:
        raise _unauthorized("Account has no email address")

    user = AuthenticatedUser(id=UUID(str(response.user.id)), email=response.user.email)

    # `public.users` is provisioned here rather than by a trigger on
    # `auth.users`, per the decision recorded in architecture.md. Nothing the
    # caller can do works without the row: `chat_threads.user_id` references it.
    try:
        await upsert_user(service_client, user.id, user.email)
    except APIError as exc:
        log.warning("user_upsert_failed", user_id=str(user.id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Could not load your account"
        ) from exc

    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
UserClient = Annotated[AsyncClient, Depends(get_user_client)]
