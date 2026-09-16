import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, now_timestamp, uuid_pk

if TYPE_CHECKING:
    from app.database.models.chat_thread import ChatThread


class User(Base):
    """One row per authenticated user, keyed by Supabase `auth.users.id`.

    This is `public.users` — our application row — distinct from `auth.users`,
    which Supabase owns. The foreign key between them lives in the migration:
    `auth.users` must not appear in our metadata, or autogenerate would try to
    create it.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now_timestamp()

    threads: Mapped[list["ChatThread"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
