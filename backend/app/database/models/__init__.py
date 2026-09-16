"""SQLAlchemy models — the source of truth for the Supabase schema.

Alembic autogenerates candidate migrations from `Base.metadata`, which is only
complete if every model module has been imported. Importing this package is what
guarantees that, so `alembic/env.py` should import from here and nowhere deeper.

Postgres features that autogenerate cannot infer are written explicitly in the
migration instead: `create extension vector`, the `public.users.id` ->
`auth.users.id` foreign key, and RLS enablement plus policies on the user-owned
tables.
"""

from app.database.models.base import Base
from app.database.models.chat_message import ChatMessage, MessageRole
from app.database.models.chat_thread import ChatThread
from app.database.models.document_chunk import DocumentChunk
from app.database.models.message_citation import MessageCitation
from app.database.models.source_document import SourceDocument
from app.database.models.user import User

__all__ = [
    "Base",
    "ChatMessage",
    "ChatThread",
    "DocumentChunk",
    "MessageCitation",
    "MessageRole",
    "SourceDocument",
    "User",
]
