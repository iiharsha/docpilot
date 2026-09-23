"""What `chats.insert_turn` sends to PostgREST.

Elsewhere the suite patches `app.database.chats` rather than faking the query
builder. This is the exception: the claim under test is about the request
itself — a turn goes out as one insert, so it cannot be half stored — and no
layer above this one can see that.
"""

import asyncio
import uuid

from app.database import chats


class RecordingClient:
    """Stands in for the Supabase client just far enough to record inserts."""

    def __init__(self) -> None:
        self.inserts: list[tuple[str, object]] = []
        self._table = ""

    def table(self, name: str) -> "RecordingClient":
        self._table = name
        return self

    def insert(self, rows: object) -> "RecordingClient":
        self.inserts.append((self._table, rows))
        return self

    async def execute(self) -> None:
        return None


def test_a_turn_is_one_insert_of_the_question_then_the_answer():
    client = RecordingClient()
    thread_id = uuid.uuid4()

    asyncio.run(chats.insert_turn(client, thread_id, 4, "Revenue?", "$391bn."))

    # One request, so one statement: the pair is stored whole or not at all.
    assert client.inserts == [
        (
            "chat_messages",
            [
                {
                    "thread_id": str(thread_id),
                    "role": "user",
                    "sequence": 4,
                    "content": "Revenue?",
                },
                {
                    "thread_id": str(thread_id),
                    "role": "assistant",
                    "sequence": 5,
                    "content": "$391bn.",
                },
            ],
        )
    ]
