"""One chat turn, end to end.

The route has already authenticated the caller and proven they own the thread,
so by the time this runs the only failures left are database ones — and a
`StreamingResponse` has sent its status line before the first line of this
generator executes. `app.errors` says the same thing from the other side: an
exception handler cannot relabel a response that has already started. So
failures here are reported as an `error` part rather than a status code.

Everything below `_stub_answer` is the real shape of a turn. `_stub_answer`
itself is the part M4 deletes, once the PydanticAI agent produces the deltas.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

import structlog
from supabase import AsyncClient

from app.api.schemas import Thread
from app.chat import streaming
from app.database import chats

log = structlog.get_logger(__name__)

# Bounded like `ThreadCreate.title`, so the two agree on what a title can be.
TITLE_MAX_LENGTH = 200

_STUB_CHUNKS = (
    "This is a stubbed answer. ",
    "Retrieval over the filings corpus is not wired up yet, ",
    "so nothing here is grounded in a real document — ",
    "and no citations are attached.\n\n",
    "Once ingestion and hybrid search land, this turn will answer from the ",
    "10-K passages it retrieves and cite each claim.",
)


async def _stub_answer() -> AsyncIterator[str]:
    """Canned deltas, paced so the browser visibly streams.

    Deleted in M4. The sleep is the point: without it the whole answer lands in
    one frame and a buffering bug anywhere in the chain would go unnoticed.
    """
    for chunk in _STUB_CHUNKS:
        await asyncio.sleep(0.04)
        yield chunk


def thread_title(question: str) -> str:
    """A sidebar label derived from the thread's first question."""
    title = " ".join(question.split())
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    return title[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


async def _persist_turn(
    client: AsyncClient, thread: Thread, question: str, sequence: int, answer: str
) -> None:
    """Title a new thread, then store the question and the answer it produced.

    Service client: migration 0001 declares select policies only, so there is no
    insert policy a user-scoped client could satisfy. The thread was proven to
    belong to the caller before any of this ran.

    The title goes first so that the turn's own write is the last thing that can
    fail. Any failure then means nothing of the turn was stored, which is what
    the client's `error` part claims — the other way round, a failed rename
    after a stored turn would tell the analyst to re-ask a question whose answer
    is already in the thread.
    """
    # Threads are created untitled and named from whatever is asked first.
    if thread.title is None:
        await chats.set_thread_title(client, thread.id, thread_title(question))

    await chats.insert_turn(client, thread.id, sequence, question, answer)


async def run_turn(
    client: AsyncClient, thread: Thread, question: str
) -> AsyncIterator[str]:
    """Stream an answer to `question`, then persist the turn."""
    # The row's own id is assigned by `gen_random_uuid()` on insert; this one
    # names the message *in the stream*, which the client needs before there is
    # anything to store. One text block, so it doubles as the block id.
    message_id = str(uuid.uuid4())

    yield streaming.sse(streaming.start(message_id))
    yield streaming.sse(streaming.text_start(message_id))

    answer: list[str] = []
    try:
        sequence = await chats.next_sequence(client, thread.id)

        async for delta in _stub_answer():
            answer.append(delta)
            yield streaming.sse(streaming.text_delta(message_id, delta))

        yield streaming.sse(streaming.text_end(message_id))

        # Before `finish`, not after: the client reads that part as the turn
        # being safely stored, and a write that failed afterwards could no
        # longer be reported. architecture.md's rule — persist only a completed
        # run — means a failed turn also drops the question; revisit in M4.
        await _persist_turn(client, thread, question, sequence, "".join(answer))
    except Exception:
        # Deliberately broad, and deliberately not re-raised. Past the first
        # byte an in-band error part is the only way left to tell the client
        # anything at all; letting this propagate would truncate the stream and
        # look to the browser like a network failure.
        log.exception("chat_turn_failed", thread_id=str(thread.id))
        yield streaming.sse(
            streaming.error("Could not finish answering. Please try again.")
        )
        return

    yield streaming.sse(streaming.finish())
    yield streaming.DONE
