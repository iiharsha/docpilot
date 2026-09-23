"""One filing's document row and chunks, written to Postgres in one transaction.

This goes through SQLAlchemy over `DATABASE_URL`, not the Supabase service
client: replacing a filing means an upsert, a delete and an insert that must
commit together, and PostgREST runs each request in a transaction of its own.
Split across three, a failed insert would leave a filing with no chunks — and
a filing that is briefly missing is one an analyst's question can miss.
"""

import uuid
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Connection, Engine, create_engine, delete, func, insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database.models import DocumentChunk, SourceDocument
from ingest.chunker import Chunk
from ingest.metadata import Filing

_DOCUMENTS = SourceDocument.__table__
_CHUNKS = DocumentChunk.__table__


def create_ingest_engine() -> Engine:
    """An engine on `DATABASE_URL`, which must be a session connection.

    psycopg prepares a statement once it has run a few times on a connection,
    and Supabase's transaction pooler (port 6543) hands the next transaction a
    different server connection, where that statement does not exist. The same
    rule as `alembic/env.py`, for a different reason.
    """
    url = urlsplit(settings.database_url)
    if url.hostname and "pooler.supabase.com" in url.hostname and url.port == 6543:
        raise RuntimeError(
            "DATABASE_URL points at the Supabase transaction pooler (port 6543). "
            "Ingestion needs a session connection: the session pooler (port 5432) "
            "or the direct connection (db.<project-ref>.supabase.co:5432)."
        )
    return create_engine(settings.sqlalchemy_database_url, poolclass=NullPool)


def document_row(filing: Filing, markdown: str) -> dict[str, Any]:
    return {
        "accession_number": filing.accession_number,
        "cik": filing.cik,
        "ticker": filing.ticker,
        "company_name": filing.company_name,
        "form_type": filing.form_type,
        "filing_date": filing.filing_date,
        "period_end_date": filing.period_end_date,
        "fiscal_year": filing.fiscal_year,
        "source_url": filing.source_url,
        "markdown": markdown,
    }


def chunk_rows(
    filing: Filing, chunks: list[Chunk], vectors: list[list[float]]
) -> list[dict[str, Any]]:
    """`document_chunks` rows, without `document_id`: `store_filing` adds it."""
    rows = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        metadata: dict[str, Any] = {
            "ticker": filing.ticker,
            "company": filing.company_name,
            "form_type": filing.form_type,
            # An int, not a string: JSONB containment (`@>`) compares types,
            # so `{"fiscal_year": "2024"}` would match nothing.
            "fiscal_year": filing.fiscal_year,
            "accession": filing.accession_number,
            "chunk_type": chunk.chunk_type,
            # `content[prefix_len:]` is `markdown[start:end]` without its page
            # markers — so any stored chunk can be checked against its filing.
            "prefix_len": chunk.prefix_len,
            "start": chunk.start,
            "end": chunk.end,
        }
        if chunk.table_part:
            metadata["table_part"], metadata["table_parts"] = chunk.table_part
        rows.append(
            {
                "chunk_index": index,
                "content": chunk.content,
                "token_count": chunk.token_count,
                "section": chunk.section,
                "page": chunk.page,
                "metadata": metadata,
                "embedding": vector,
            }
        )
    return rows


def store_filing(
    connection: Connection, document: dict[str, Any], chunks: list[dict[str, Any]]
) -> uuid.UUID:
    """Replace one filing's document row and chunks; returns the document id.

    Runs inside the caller's transaction and never begins one, so a test can
    drive it, and a filing is replaced whole or not at all. The upsert keeps
    the row — and its id — so past citations keep their `document_id`.
    Their `chunk_id`s go null instead (`on delete set null`), and the
    citation's own copy of the passage is what still renders.
    """
    upsert = pg_insert(_DOCUMENTS).values(document)
    upsert = upsert.on_conflict_do_update(
        index_elements=[_DOCUMENTS.c.accession_number],
        set_={
            **{
                name: upsert.excluded[name]
                for name in document
                if name != "accession_number"
            },
            # A server default only applies on insert.
            "ingested_at": func.now(),
        },
    ).returning(_DOCUMENTS.c.id)
    document_id = connection.execute(upsert).scalar_one()
    connection.execute(delete(_CHUNKS).where(_CHUNKS.c.document_id == document_id))
    connection.execute(
        insert(_CHUNKS), [{**row, "document_id": document_id} for row in chunks]
    )
    return document_id


def vacuum(engine: Engine) -> None:
    """Reclaim the chunks a full run replaced and refresh planner statistics.

    Delete-then-insert leaves every replaced row dead until vacuumed, and
    retrieval's query plans depend on current statistics. VACUUM cannot run
    inside a transaction, hence autocommit.
    """
    with engine.connect() as connection:
        connection.execution_options(isolation_level="AUTOCOMMIT")
        for table in (_DOCUMENTS.name, _CHUNKS.name):
            connection.execute(text(f"VACUUM ANALYZE {table}"))
