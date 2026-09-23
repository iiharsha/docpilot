import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, now_timestamp, uuid_pk
from app.database.models.user import User

if TYPE_CHECKING:
    from app.database.models.chat_message import ChatMessage


class ChatThread(Base):
    """A conversation. Titled from its first user message."""

    __tablename__ = "chat_threads"
    __table_args__ = (
        Index("ix_chat_threads_user_id_updated_at", "user_id", text("updated_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now_timestamp()
    # No `onupdate=`: that is applied by the ORM in Python, and every write in
    # this service goes through PostgREST, so it never fired. Migrations 0002
    # and 0003 move this column with triggers — on any update of this table, and
    # on an insert into `chat_messages` — which is the only place the rule holds
    # for every writer. `ix_chat_threads_user_id_updated_at` orders on it.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    owner: Mapped[User] = relationship(back_populates="threads")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.sequence",
    )
