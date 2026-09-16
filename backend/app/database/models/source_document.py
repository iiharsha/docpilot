import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, now_timestamp, uuid_pk

if TYPE_CHECKING:
    from app.database.models.document_chunk import DocumentChunk


class SourceDocument(Base):
    """One SEC filing, with the normalized Markdown we chunk and cite from.

    Keeping the Markdown lets us re-chunk and re-embed without going back to the
    downloaded HTML, and lets a citation be verified against the extracted text
    the answer actually came from.
    """

    __tablename__ = "source_documents"
    __table_args__ = (
        Index("ix_source_documents_ticker_fiscal_year", "ticker", "fiscal_year"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # EDGAR's per-filing identifier. Ingestion is idempotent on this.
    accession_number: Mapped[str] = mapped_column(
        String(25), nullable=False, unique=True
    )
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    form_type: Mapped[str] = mapped_column(String(10), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Period covered, not the filing date: a 10-K filed in Oct 2025 for the year
    # ending Sep 2025 is FY2025.
    period_end_date: Mapped[date | None] = mapped_column(Date)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = now_timestamp()

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )
