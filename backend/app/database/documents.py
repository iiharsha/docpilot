"""Reads of the filing corpus: filings and their chunks, for retrieval.

`ingest/store.py` writes these tables and this module reads them, both over
`DATABASE_URL` (`database/engine.py`) rather than PostgREST. RLS is enabled on
the corpus tables with no read policies (migration 0001), so no user's key can
read them — only the backend's own connection. `source_documents.markdown`, a
whole filing, is never selected.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# (ticker, fiscal year, form type): what names one filing in the corpus.
FilingKey = tuple[str, int, str]


@dataclass(frozen=True)
class Filing:
    """A stored filing's identity — what a citation names — without its text."""

    id: uuid.UUID
    ticker: str
    company_name: str
    form_type: str
    fiscal_year: int
    period_end_date: date | None
    filing_date: date
    accession_number: str
    source_url: str


@dataclass(frozen=True)
class ChunkRef:
    """Where a chunk sits in its filing: what a search ranks, and all that
    finding its context takes."""

    document_id: uuid.UUID
    chunk_index: int
    # Piece n of m, when the chunk holds part of a table too large to keep whole.
    table_part: tuple[int, int] | None = None


@dataclass(frozen=True)
class Chunk:
    """A stored passage, with the citation unit it is cited by."""

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    section: str | None
    page: str | None
    content: str
    token_count: int
    table_part: tuple[int, int] | None = None


@dataclass(frozen=True)
class Passage:
    """A retrieved chunk and the context it is read with."""

    chunk: Chunk
    # The chunks either side and every other part of a split table, in filing
    # order. A chunk's neighbours carry what its edges cut off, and a later
    # piece of a table repeats the header but not the rows above it.
    context: tuple[Chunk, ...]


_FILINGS = text("""
    SELECT d.id, d.ticker, d.company_name, d.form_type, d.fiscal_year,
           d.period_end_date, d.filing_date, d.accession_number, d.source_url
    FROM unnest(
        CAST(:tickers AS text[]),
        CAST(:fiscal_years AS integer[]),
        CAST(:form_types AS text[])
    ) AS wanted (ticker, fiscal_year, form_type)
    JOIN source_documents AS d USING (ticker, fiscal_year, form_type)
""")

_CHUNKS = text("""
    SELECT c.id, c.document_id, c.chunk_index, c.section, c.page, c.content,
           c.token_count,
           (c.metadata->>'table_part')::integer AS table_part,
           (c.metadata->>'table_parts')::integer AS table_parts
    FROM unnest(CAST(:document_ids AS uuid[]), CAST(:chunk_indexes AS integer[]))
        AS wanted (document_id, chunk_index)
    JOIN document_chunks AS c USING (document_id, chunk_index)
""")


async def find_filings(
    connection: AsyncConnection, keys: Iterable[FilingKey]
) -> dict[FilingKey, Filing]:
    """The stored filing for each key; a key the corpus has none for is left out.

    There is at most one per key: `data/download.py` takes one 10-K per company
    and fiscal year.
    """
    keys = list(keys)
    result = await connection.execute(
        _FILINGS,
        {
            "tickers": [ticker for ticker, _, _ in keys],
            "fiscal_years": [fiscal_year for _, fiscal_year, _ in keys],
            "form_types": [form_type for _, _, form_type in keys],
        },
    )
    filings = [Filing(**row._mapping) for row in result]
    return {
        (filing.ticker, filing.fiscal_year, filing.form_type): filing
        for filing in filings
    }


async def read_passages(
    connection: AsyncConnection, hits: Iterable[ChunkRef]
) -> dict[ChunkRef, Passage]:
    """Each hit's chunk with its context, all read in one query."""
    hits = list(hits)
    positions = sorted(
        {(hit.document_id, index) for hit in hits for index in _context_indexes(hit)}
    )
    result = await connection.execute(
        _CHUNKS,
        {
            "document_ids": [document_id for document_id, _ in positions],
            "chunk_indexes": [index for _, index in positions],
        },
    )
    chunks = {
        (chunk.document_id, chunk.chunk_index): chunk for chunk in map(_chunk, result)
    }
    return {hit: _passage(hit, chunks) for hit in hits}


def _context_indexes(hit: ChunkRef) -> range:
    """The chunk indexes read for a hit: its own, one either side, and every
    part of its table.

    The chunker gives each piece of a split table a chunk of its own, in order,
    so piece n of m at index i has the others at i - n + 1 … i + m - n. Indexes
    past a filing's last chunk simply match no row.
    """
    first, last = hit.chunk_index - 1, hit.chunk_index + 1
    if hit.table_part is not None:
        part, parts = hit.table_part
        first = min(first, hit.chunk_index - part + 1)
        last = max(last, hit.chunk_index + parts - part)
    return range(max(first, 0), last + 1)


def _passage(hit: ChunkRef, chunks: Mapping[tuple[uuid.UUID, int], Chunk]) -> Passage:
    context = tuple(
        chunks[hit.document_id, index]
        for index in _context_indexes(hit)
        if index != hit.chunk_index and (hit.document_id, index) in chunks
    )
    return Passage(chunks[hit.document_id, hit.chunk_index], context)


def _chunk(row: Any) -> Chunk:
    return Chunk(
        id=row.id,
        document_id=row.document_id,
        chunk_index=row.chunk_index,
        section=row.section,
        page=row.page,
        content=row.content,
        token_count=row.token_count,
        table_part=(row.table_part, row.table_parts) if row.table_part else None,
    )
