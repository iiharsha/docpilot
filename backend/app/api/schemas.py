"""Wire models for the HTTP API.

Rows arrive from PostgREST in snake_case and `frontend/src/lib/api.ts` declares
camelCase, so `WireModel` renames on the way out only. The asymmetry is
deliberate: responses serialise as camelCase, while request bodies still
validate against the snake_case field names, so the API never quietly accepts
two spellings of the same field.

`chat.messages.StreamRequest` is the one exception and does not build on
`WireModel`. The AI SDK composes that request itself and sends `threadId` —
which is also what architecture.md specifies — so it has to validate camelCase
too. Every request body we control stays snake_case.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.database.models.chat_message import MessageRole


class WireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(serialization_alias=to_camel)
    )


class Thread(WireModel):
    """A conversation, as the thread sidebar sees it. Never carries `user_id`."""

    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ThreadCreate(WireModel):
    # Titles are generated from the first message; a caller-supplied one is a
    # label, not free-form content, so it is bounded at the boundary.
    title: str | None = Field(default=None, max_length=200)


class Citation(WireModel):
    """A claim in an answer, tied to the passage that supports it.

    Denormalised at answer time (see `MessageCitation`) so it renders standalone
    after the source filing is re-ingested.
    """

    marker: int
    excerpt: str
    section: str | None
    # Text, not an integer: filings label pages "F-12" as often as "42".
    # `api.ts` types this `number | null`; the TypeScript is what's wrong.
    page: str | None
    ticker: str
    company_name: str
    form_type: str
    filing_date: date
    # Nullable: `fiscal_year` comes from `source_documents`, and
    # `message_citations.document_id` is ON DELETE SET NULL by design.
    fiscal_year: int | None


class ChatMessage(WireModel):
    """One stored turn in a thread."""

    id: UUID
    role: MessageRole
    content: str
    sequence: int
    created_at: datetime
    # Declared and empty until Phase 3 selects the citation rows: `api.ts` types
    # this non-optional, so omitting the key makes the first `.map()` throw.
    citations: list[Citation] = Field(default_factory=list)
