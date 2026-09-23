"""Persistence for chat threads and their messages.

PostgREST only: these helpers take whichever client the caller decided is right
and hand back rows. That choice — and so whether RLS applies — is a routing
decision that belongs with the routes, and HTTP status codes are not this
layer's business either.

Columns are listed explicitly rather than selected with `*`, so a column added
later is not shipped to the browser by accident.
"""

import uuid
from typing import Any

from supabase import AsyncClient

from app.database.models.chat_message import MessageRole

THREAD_COLUMNS = "id,title,created_at,updated_at"
# `user_id` is for the ownership check only; it never reaches a response model.
OWNED_THREAD_COLUMNS = f"{THREAD_COLUMNS},user_id"
MESSAGE_COLUMNS = "id,role,content,sequence,created_at"


async def list_threads(client: AsyncClient, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """The user's threads, most recently updated first."""
    # RLS already scopes this to `auth.uid()` for a user-scoped client. The
    # filter is here so the query stays correct if the client ever changes.
    response = await (
        client.table("chat_threads")
        .select(THREAD_COLUMNS)
        .eq("user_id", str(user_id))
        .order("updated_at", desc=True)
        .execute()
    )
    return response.data


async def create_thread(
    client: AsyncClient, user_id: uuid.UUID, title: str | None
) -> dict[str, Any]:
    """Insert a thread owned by `user_id` and return the stored row.

    Needs the service client: migration 0001 keeps writes backend-only, so there
    is no insert policy a user-scoped client could satisfy.
    """
    response = await (
        client.table("chat_threads")
        .insert({"user_id": str(user_id), "title": title})
        .select(THREAD_COLUMNS)
        .execute()
    )
    return response.data[0]


async def fetch_thread(
    client: AsyncClient, thread_id: uuid.UUID
) -> dict[str, Any] | None:
    """One thread including its owner, or None if there is no such thread.

    `maybe_single().execute()` returns None *itself* when nothing matches — not
    a response with empty `data` — so the caller must test the response.
    """
    response = await (
        client.table("chat_threads")
        .select(OWNED_THREAD_COLUMNS)
        .eq("id", str(thread_id))
        .maybe_single()
        .execute()
    )
    return response.data if response is not None else None


async def list_messages(
    client: AsyncClient, thread_id: uuid.UUID
) -> list[dict[str, Any]]:
    """A thread's stored turns in order, oldest first."""
    response = await (
        client.table("chat_messages")
        .select(MESSAGE_COLUMNS)
        .eq("thread_id", str(thread_id))
        .order("sequence")
        .execute()
    )
    return response.data


async def next_sequence(client: AsyncClient, thread_id: uuid.UUID) -> int:
    """The `sequence` a message appended to this thread should take.

    The column has no default and `uq_chat_messages_thread_sequence` is the only
    ordering guarantee, so the writer has to supply it. Empty thread starts at 0.
    """
    response = await (
        client.table("chat_messages")
        .select("sequence")
        .eq("thread_id", str(thread_id))
        .order("sequence", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0]["sequence"] + 1 if response.data else 0


async def insert_turn(
    client: AsyncClient,
    thread_id: uuid.UUID,
    sequence: int,
    question: str,
    answer: str,
) -> None:
    """Store a question and its answer at `sequence` and `sequence + 1`.

    One request, so one `INSERT`: the pair is stored whole or not at all. As two
    requests, a failure of the second — or the browser leaving between them,
    which cancels the stream mid-write — would keep a question in the history
    with no answer after it.

    Needs the service client, like every other write here: migration 0001
    declares select policies only.

    `parts` is left null on purpose. While answers are plain text, `content`
    round-trips exactly, and any `parts` payload written now would be a guess at
    a shape citations have not yet fixed.
    """
    rows = [
        {
            "thread_id": str(thread_id),
            "role": role.value,
            "sequence": sequence + offset,
            "content": content,
        }
        for offset, (role, content) in enumerate(
            [(MessageRole.USER, question), (MessageRole.ASSISTANT, answer)]
        )
    ]
    await client.table("chat_messages").insert(rows).execute()


async def set_thread_title(
    client: AsyncClient, thread_id: uuid.UUID, title: str
) -> None:
    """Name a thread. Service client only, for the same reason as the inserts."""
    await (
        client.table("chat_threads")
        .update({"title": title})
        .eq("id", str(thread_id))
        .execute()
    )
