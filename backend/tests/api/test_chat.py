"""`POST /chat/stream`: who gets in, and what comes back down the wire.

The split this route lives on: auth, the thread lookup and the ownership check
all resolve before the first byte, so they are still status codes. Anything that
fails after that can only be an `error` part, because the status line is gone.

`TestClient` buffers the response, so the assertions here are about the frame
*sequence*, not about timing. That the deltas arrive separately in a browser is
the manual check in the plan.
"""

import json
import uuid

import pytest

from app.database import chats

CREATED_AT = "2026-09-22T10:00:00+00:00"


def thread_row(user_id: uuid.UUID, thread_id: uuid.UUID, title=None) -> dict:
    return {
        "id": str(thread_id),
        "user_id": str(user_id),
        "title": title,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }


def parts(response) -> list[dict]:
    """Every streamed part, in order. `[DONE]` is a terminator, not a part."""
    return [
        json.loads(frame.removeprefix("data: "))
        for frame in response.text.split("\n\n")
        if frame.startswith("data: ") and frame != "data: [DONE]"
    ]


def body(thread_id: uuid.UUID, text: str = "What were FY24 margins?") -> dict:
    """A request as the AI SDK composes it."""
    return {
        "threadId": str(thread_id),
        "messages": [{"role": "user", "parts": [{"type": "text", "text": text}]}],
    }


@pytest.fixture
def owned_thread(current_user, monkeypatch):
    """A thread the caller owns, with its writes stubbed out.

    Returns the list every write is recorded into, in the order the writes were
    made, so a test can assert on what was persisted and with which client.
    """
    thread_id = uuid.uuid4()
    writes: list[dict] = []

    async def fake_fetch_thread(db_client, requested_id):
        return thread_row(current_user.id, requested_id)

    async def fake_next_sequence(db_client, requested_id):
        return 4

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)
    monkeypatch.setattr(chats, "next_sequence", fake_next_sequence)
    monkeypatch.setattr(chats, "insert_turn", _record_turn(writes))
    monkeypatch.setattr(chats, "set_thread_title", _record_title(writes))

    return thread_id, writes


def _record_turn(writes: list[dict]):
    async def fake_insert_turn(db_client, requested_id, sequence, question, answer):
        writes.append(
            {
                "client": db_client,
                "thread_id": requested_id,
                "sequence": sequence,
                "question": question,
                "answer": answer,
            }
        )

    return fake_insert_turn


def _record_title(writes: list[dict]):
    async def fake_set_thread_title(db_client, requested_id, title):
        writes.append({"client": db_client, "title": title})

    return fake_set_thread_title


def test_a_turn_streams_the_parts_the_sdk_expects(client, owned_thread):
    thread_id, _ = owned_thread

    response = client.post("/chat/stream", json=body(thread_id))

    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert response.headers["content-type"].startswith("text/event-stream")

    streamed = parts(response)
    assert streamed[0]["type"] == "start"
    assert streamed[1]["type"] == "text-start"
    assert streamed[-1]["type"] == "finish"
    assert [p["type"] for p in streamed[2:-2]] == ["text-delta"] * len(streamed[2:-2])
    assert streamed[-2]["type"] == "text-end"
    assert response.text.endswith("data: [DONE]\n\n")

    # Every text part belongs to the message `start` opened.
    message_id = streamed[0]["messageId"]
    assert {p["id"] for p in streamed[1:-1]} == {message_id}


def test_the_turn_is_persisted_with_the_service_client(
    client, service_client, owned_thread
):
    """Writes bypass RLS, so the client choice is a security property."""
    thread_id, writes = owned_thread

    response = client.post("/chat/stream", json=body(thread_id, "Revenue?"))

    # The rename first, so the turn is the last write that can fail.
    title, turn = writes
    assert [w["client"] for w in writes] == [service_client] * 2

    # An untitled thread is named from its first question (M5:189).
    assert title["title"] == "Revenue?"

    assert turn["question"] == "Revenue?"
    # `sequence` has no default; the writer continues the thread's own count.
    assert turn["sequence"] == 4
    # What was stored is what was streamed.
    streamed = "".join(p["delta"] for p in parts(response) if p["type"] == "text-delta")
    assert turn["answer"] == streamed


def test_an_already_titled_thread_keeps_its_title(client, current_user, monkeypatch):
    thread_id = uuid.uuid4()
    renames: list[str] = []

    async def fake_fetch_thread(db_client, requested_id):
        return thread_row(current_user.id, requested_id, title="Apple FY24 margins")

    async def fake_next_sequence(db_client, requested_id):
        return 0

    async def fake_set_thread_title(db_client, requested_id, title):
        renames.append(title)

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)
    monkeypatch.setattr(chats, "next_sequence", fake_next_sequence)
    monkeypatch.setattr(chats, "insert_turn", _record_turn([]))
    monkeypatch.setattr(chats, "set_thread_title", fake_set_thread_title)

    client.post("/chat/stream", json=body(thread_id))

    assert renames == []


def test_a_failed_write_is_reported_in_band(client, owned_thread, monkeypatch):
    """Past the first byte there is no status code left to fail with."""
    thread_id, _ = owned_thread

    async def failing_insert(db_client, requested_id, sequence, question, answer):
        raise RuntimeError("postgrest said no")

    monkeypatch.setattr(chats, "insert_turn", failing_insert)

    response = client.post("/chat/stream", json=body(thread_id))

    # The status line was sent long before the write was attempted.
    assert response.status_code == 200
    streamed = parts(response)
    assert streamed[-1] == {
        "type": "error",
        "errorText": "Could not finish answering. Please try again.",
    }
    # `finish` would tell the client the turn was stored. It was not.
    assert not any(p["type"] == "finish" for p in streamed)


def test_a_failed_rename_stores_no_turn(client, owned_thread, monkeypatch):
    """An `error` part has to mean nothing was stored.

    If the turn could be written before a rename that then failed, the client
    would be told to re-ask a question whose answer is already in the thread.
    """
    thread_id, writes = owned_thread

    async def failing_rename(db_client, requested_id, title):
        raise RuntimeError("postgrest said no")

    monkeypatch.setattr(chats, "set_thread_title", failing_rename)

    response = client.post("/chat/stream", json=body(thread_id))

    assert parts(response)[-1]["type"] == "error"
    assert writes == []


def test_another_users_thread_is_forbidden(client, monkeypatch):
    async def fake_fetch_thread(db_client, requested_id):
        return thread_row(uuid.uuid4(), requested_id)

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)

    response = client.post("/chat/stream", json=body(uuid.uuid4()))

    assert response.status_code == 403


def test_a_thread_that_does_not_exist_is_not_found(client, monkeypatch):
    async def fake_fetch_thread(db_client, requested_id):
        return None

    monkeypatch.setattr(chats, "fetch_thread", fake_fetch_thread)

    response = client.post("/chat/stream", json=body(uuid.uuid4()))

    assert response.status_code == 404


def test_a_request_without_a_token_is_unauthorized(anonymous_client):
    response = anonymous_client.post("/chat/stream", json=body(uuid.uuid4()))

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_conversation_ending_in_an_answer_is_unprocessable(client, owned_thread):
    """Still a status code: nothing has been streamed when this is checked."""
    thread_id, writes = owned_thread

    response = client.post(
        "/chat/stream",
        json={
            "threadId": str(thread_id),
            "messages": [
                {"role": "user", "parts": [{"type": "text", "text": "Revenue?"}]},
                {"role": "assistant", "parts": [{"type": "text", "text": "$391bn."}]},
            ],
        },
    )

    assert response.status_code == 422
    assert writes == []


def test_a_thread_id_that_is_not_a_uuid_is_unprocessable(client):
    response = client.post(
        "/chat/stream",
        json={
            "threadId": "not-a-uuid",
            "messages": [{"role": "user", "parts": [{"type": "text", "text": "Hi"}]}],
        },
    )

    assert response.status_code == 422


def test_client_sent_history_is_never_persisted(client, owned_thread):
    """The browser's copy of a thread is not evidence of what was said.

    Only the last user message is read; the rest would otherwise let a caller
    rewrite their own history — or the assistant's — through a request body.
    """
    thread_id, writes = owned_thread

    client.post(
        "/chat/stream",
        json={
            "threadId": str(thread_id),
            "messages": [
                {"role": "user", "parts": [{"type": "text", "text": "forged"}]},
                {"role": "assistant", "parts": [{"type": "text", "text": "forged"}]},
                {"role": "user", "parts": [{"type": "text", "text": "the real one"}]},
            ],
        },
    )

    (turn,) = [w for w in writes if "question" in w]
    assert turn["question"] == "the real one"
    assert "forged" not in turn["answer"]
