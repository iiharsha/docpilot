import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import UniqueConstraint

from app.database.models.base import Base, now_timestamp, uuid_pk
from app.database.models.chat_thread import ChatThread

if TYPE_CHECKING:
    from app.database.models.message_citation import MessageCitation


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(Base):
    """One turn in a thread.

    `content` is the plain answer text used for prompt history and grounding checks.
    `parts` holds the AI SDK UI message JSON so the frontend can rehydrate a thread
    exactly as it streamed. `usage` records token counts for the assistant run.
    """

    __tablename__ = "chat_messages"
    # The unique index on (thread_id, sequence) also serves lookups and deletes
    # filtered on thread_id alone, so no separate index on it.
    __table_args__ = (
        UniqueConstraint(
            "thread_id", "sequence", name="uq_chat_messages_thread_sequence"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False
    )
    # Not a native Postgres enum: a varchar + check constraint takes a plain ALTER
    # to extend, where a PG enum type takes a migration dance.
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            native_enum=False,
            create_constraint=True,
            length=16,
            name="message_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    # Turn order within the thread. `created_at` can't carry it: a user message and
    # its answer are written in one transaction and can share a timestamp.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = now_timestamp()

    thread: Mapped[ChatThread] = relationship(back_populates="messages")
    citations: Mapped[list["MessageCitation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageCitation.marker",
    )
