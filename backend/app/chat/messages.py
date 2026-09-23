"""The AI SDK's UI message format, at the request boundary.

The browser posts its whole visible conversation. This module takes only the
question out of it: the thread's real history is in Postgres, and rebuilding a
prompt from the client's copy would let anyone rewrite what they had previously
asked — and what the assistant had previously answered — by editing a request
body. Everything but the last user message is therefore dropped on the floor.

The parts array carries more kinds than text (files, tool calls, reasoning), and
the set grows between SDK releases. Unknown keys and unknown part types are
ignored rather than rejected, so a client upgrade cannot 422 a valid question.
"""

from uuid import UUID

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class MessagePart(BaseModel):
    """One part of a UI message. Only `text` parts carry a question."""

    model_config = ConfigDict(extra="ignore")

    type: str
    # Absent on every part type except `text`.
    text: str | None = None


class UIMessage(BaseModel):
    """A message as the AI SDK's `useChat` holds it."""

    model_config = ConfigDict(extra="ignore")

    role: str
    parts: list[MessagePart]


class StreamRequest(BaseModel):
    """The body of `POST /chat/stream`.

    Unlike `api.schemas.WireModel`, this validates *camelCase* as well as
    renaming on the way out: the AI SDK builds the request itself and sends
    `threadId`, which is also what architecture.md specifies. `WireModel` renames
    on serialisation only, so a request model built on it would demand
    `thread_id` and reject the SDK's body.

    The SDK also sends `id`, `trigger` and `messageId`. They describe a chat
    session the backend does not track, so they are ignored by default.
    """

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel, serialization_alias=to_camel
        )
    )

    thread_id: UUID
    messages: list[UIMessage] = Field(min_length=1)


def question_from(messages: list[UIMessage]) -> str:
    """The question this turn has to answer.

    Raises `ValueError` when the request does not end in one — the caller turns
    that into a 422, which it still can because nothing has been streamed yet.
    """
    last = messages[-1]
    if last.role != "user":
        raise ValueError(
            f"Expected the last message to be from the user, got {last.role!r}"
        )

    question = "".join(
        part.text for part in last.parts if part.type == "text" and part.text
    ).strip()
    if not question:
        raise ValueError("The last message has no text to answer")
    return question
