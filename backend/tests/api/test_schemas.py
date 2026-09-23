"""The wire contract `frontend/src/lib/api.ts` is typed against.

The frontend declares `Thread` as `{id, title, createdAt, updatedAt}` and
`ChatMessage` as `{id, role, content, sequence, createdAt, citations}`. Nothing
else checks that the Python models still serialise to exactly those keys, so a
renamed or added field shows up here rather than as an undefined in the browser.
"""

import uuid

from app.api.schemas import ChatMessage, Thread

TIMESTAMP = "2026-09-22T10:00:00+00:00"


def test_thread_serialises_the_keys_the_frontend_declares():
    # A row as PostgREST returns it, `user_id` included.
    thread = Thread.model_validate(
        {
            "id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "title": "Apple FY24 margins",
            "created_at": TIMESTAMP,
            "updated_at": TIMESTAMP,
        }
    )

    assert set(thread.model_dump(mode="json", by_alias=True)) == {
        "id",
        "title",
        "createdAt",
        "updatedAt",
    }


def test_chat_message_serialises_the_keys_the_frontend_declares():
    message = ChatMessage.model_validate(
        {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": "Gross margin was 46.2%.",
            "sequence": 2,
            "created_at": TIMESTAMP,
        }
    )
    payload = message.model_dump(mode="json", by_alias=True)

    assert set(payload) == {
        "id",
        "role",
        "content",
        "sequence",
        "createdAt",
        "citations",
    }
    # Typed non-optional in TypeScript: the key has to be present even while
    # Phase 3 is the thing that fills it.
    assert payload["citations"] == []
