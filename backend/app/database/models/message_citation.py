import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, now_timestamp, uuid_pk
from app.database.models.chat_message import ChatMessage
from app.database.models.document_chunk import DocumentChunk
from app.database.models.source_document import SourceDocument


class MessageCitation(Base):
    """A claim in an assistant answer, tied to the passage that supports it.

    Passage text, location, and filing identity are denormalized on purpose.
    Re-ingesting a filing replaces its chunks, so `chunk_id` goes null rather than
    cascading; an answer an analyst read last month must still render its evidence
    afterwards — company, filing, date, excerpt — with no source row left to join.
    """

    __tablename__ = "message_citations"
    __table_args__ = (
        UniqueConstraint("message_id", "marker"),
        Index("ix_message_citations_chunk_id", "chunk_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    # 1-based position of the inline marker in the answer text.
    marker: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str | None] = mapped_column(Text)
    # Text, not an integer: filings label pages "F-12" or "II-3" as often as "42".
    page: Mapped[str | None] = mapped_column(Text)
    # Copied from the filing at answer time so the citation renders standalone.
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    form_type: Mapped[str] = mapped_column(String(10), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = now_timestamp()

    message: Mapped[ChatMessage] = relationship(back_populates="citations")
    chunk: Mapped[DocumentChunk | None] = relationship()
    document: Mapped[SourceDocument | None] = relationship()
