"""Thread routes: list my threads, start one, read one's history.

Ownership is the whole security story here, and RLS alone cannot tell it: a
foreign thread and a thread that does not exist both come back empty through a
user-scoped client, which collapses 403 into 404. So the guard looks the thread
up with the service client and compares owners itself, and the routes that need
nothing more than the caller's own rows keep using the user client.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from supabase import AsyncClient

from app.api.schemas import ChatMessage, Thread, ThreadCreate
from app.auth.dependencies import CurrentUser, UserClient
from app.database import chats
from app.dependencies import ServiceClient

router = APIRouter(prefix="/threads", tags=["threads"])


async def authorize_thread(
    service_client: AsyncClient, thread_id: uuid.UUID, user_id: uuid.UUID
) -> Thread:
    """Load a thread, or fail with the status the caller has earned.

    Takes ids rather than a request, so `POST /chat/stream` — which receives
    `threadId` in the body and so cannot use a `Path()` dependency — can reuse
    the same rule.
    """
    row = await chats.fetch_thread(service_client, thread_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    # PostgREST renders uuid columns as JSON strings. Comparing one to a `UUID`
    # is unequal every time, which would 403 the owner out of their own thread.
    if uuid.UUID(row["user_id"]) != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Thread belongs to another user")
    return Thread.model_validate(row)


async def get_owned_thread(
    thread_id: Annotated[uuid.UUID, Path()],
    user: CurrentUser,
    service_client: ServiceClient,
) -> Thread:
    return await authorize_thread(service_client, thread_id, user.id)


OwnedThread = Annotated[Thread, Depends(get_owned_thread)]


# "" rather than "/": `@router.get("/")` under a prefix answers `/threads` with
# a 307 to `/threads/`, which the browser client has no reason to follow.
@router.get("")
async def list_threads(user: CurrentUser, client: UserClient) -> list[Thread]:
    """The caller's threads, most recent activity first."""
    rows = await chats.list_threads(client, user.id)
    return [Thread.model_validate(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadCreate, user: CurrentUser, service_client: ServiceClient
) -> Thread:
    """Start a thread owned by the caller.

    The service client writes it: there is no insert policy to satisfy, so
    `user_id` comes from the verified token instead of from `auth.uid()`.
    """
    row = await chats.create_thread(service_client, user.id, payload.title)
    return Thread.model_validate(row)


@router.get("/{thread_id}/messages")
async def list_messages(thread: OwnedThread, client: UserClient) -> list[ChatMessage]:
    """A thread's stored history, oldest first.

    `OwnedThread` has already proven ownership, so the user client here is a
    second, independent lock: even a bug in the guard could not read another
    user's messages through it.
    """
    rows = await chats.list_messages(client, thread.id)
    return [ChatMessage.model_validate(row) for row in rows]
