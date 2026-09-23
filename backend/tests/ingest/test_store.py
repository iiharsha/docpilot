"""What `store_filing` sends to Postgres, and the rows it is given.

Like `tests/database/test_chats.py`, this records statements rather than
running them: the claim under test is about the statements — an upsert, a
delete and an insert, in that order, inside the caller's transaction — and
nothing above this layer can see them.
"""

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.config import settings
from ingest import store
from ingest.chunker import Chunk
from ingest.metadata import Filing

FILING = Filing(
    ticker="AMZN",
    cik="0001018724",
    company_name="AMAZON.COM, INC.",
    form_type="10-K",
    accession_number="0001018724-25-000004",
    filing_date=date(2025, 2, 7),
    period_end_date=date(2024, 12, 31),
    fiscal_year=2024,
    source_url="https://www.sec.gov/Archives/edgar/data/1018724/000101872425000004/amzn-20241231.htm",
)
SECTION = "Item 8. Financial Statements and Supplementary Data"
TEXT = Chunk(SECTION, "66", "The AWS segment consists of …", 0, 100, 128, 5, "text")
TABLE_PIECE = Chunk(
    SECTION, "66", "| … |\n| AWS |  |  |  |", 12, 300, 320, 9, "table", (2, 3)
)


class RecordingConnection:
    """Stands in for a SQLAlchemy `Connection` far enough to record statements."""

    def __init__(self, document_id: uuid.UUID) -> None:
        self.document_id = document_id
        self.statements: list[tuple[object, object]] = []

    def execute(self, statement, parameters=None) -> SimpleNamespace:
        self.statements.append((statement, parameters))
        return SimpleNamespace(scalar_one=lambda: self.document_id)


def _sql(statement) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def test_a_filing_is_replaced_by_an_upsert_a_delete_and_an_insert():
    document_id = uuid.uuid4()
    connection = RecordingConnection(document_id)
    rows = store.chunk_rows(FILING, [TEXT, TABLE_PIECE], [[0.1], [0.2]])

    returned = store.store_filing(
        connection, store.document_row(FILING, "# markdown"), rows
    )

    (upsert, _), (delete, _), (insert, inserted) = connection.statements
    assert returned == document_id
    assert _sql(upsert).startswith("INSERT INTO source_documents")
    assert "ON CONFLICT (accession_number) DO UPDATE SET" in _sql(upsert)
    assert _sql(upsert).endswith("RETURNING source_documents.id")
    # The delete takes the id the upsert returned, so it can only ever remove
    # this filing's chunks.
    assert _sql(delete).startswith(
        "DELETE FROM document_chunks WHERE document_chunks.document_id ="
    )
    assert delete.compile().params == {"document_id_1": document_id}
    assert _sql(insert).startswith("INSERT INTO document_chunks")
    assert [row["document_id"] for row in inserted] == [document_id, document_id]


def test_a_reingested_filing_keeps_its_id_and_is_stamped_anew():
    connection = RecordingConnection(uuid.uuid4())

    store.store_filing(connection, store.document_row(FILING, "# markdown"), [])

    upsert = _sql(connection.statements[0][0])
    updated = upsert.split("DO UPDATE SET", 1)[1]
    # Past citations keep their `document_id`: the conflict updates the row
    # instead of replacing it, and never assigns `id`.
    assert " id =" not in updated
    assert "markdown = excluded.markdown" in updated
    assert "ingested_at = now()" in updated


def test_chunk_rows_carry_the_metadata_retrieval_filters_on():
    text, piece = store.chunk_rows(FILING, [TEXT, TABLE_PIECE], [[0.1], [0.2]])

    assert text["metadata"] == {
        "ticker": "AMZN",
        "company": "AMAZON.COM, INC.",
        "form_type": "10-K",
        "fiscal_year": 2024,
        "accession": "0001018724-25-000004",
        "chunk_type": "text",
        "prefix_len": 0,
        "start": 100,
        "end": 128,
    }
    # JSONB containment is type-strict: `{"fiscal_year": "2024"}` would match nothing.
    assert type(text["metadata"]["fiscal_year"]) is int
    assert (piece["metadata"]["table_part"], piece["metadata"]["table_parts"]) == (2, 3)
    assert [row["chunk_index"] for row in (text, piece)] == [0, 1]
    assert (piece["section"], piece["page"], piece["embedding"]) == (
        SECTION,
        "66",
        [0.2],
    )


def test_the_transaction_pooler_is_refused(monkeypatch):
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql://postgres.ref:secret@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
    )

    with pytest.raises(RuntimeError, match="transaction pooler"):
        store.create_ingest_engine()
