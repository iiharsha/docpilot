"""The fan-out: every slice searched in its own filing, fused there, answered in order.

The database is patched at the `documents` and `queries` boundaries, whose own
tests cover what they send, and the embeddings client is a stand-in, so
nothing here leaves the process.
"""

import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.config import settings
from app.database import documents
from app.database.documents import Chunk, ChunkRef, Filing, Passage
from app.retrieval import queries, retriever
from app.retrieval.retriever import Slice

QUESTION = "How did iPhone net sales change?"
AAPL_2023 = uuid.UUID("33333333-3333-4333-8333-333333333333")
AAPL_2024 = uuid.UUID("44444444-4444-4444-8444-444444444444")


def _filing(document_id: uuid.UUID, fiscal_year: int) -> Filing:
    return Filing(
        id=document_id,
        ticker="AAPL",
        company_name="Apple Inc.",
        form_type="10-K",
        fiscal_year=fiscal_year,
        period_end_date=date(fiscal_year, 9, 28),
        filing_date=date(fiscal_year, 11, 1),
        accession_number=f"0000320193-{fiscal_year % 100}-000123",
        source_url="https://www.sec.gov/",
    )


FILINGS = {
    ("AAPL", 2023, "10-K"): _filing(AAPL_2023, 2023),
    ("AAPL", 2024, "10-K"): _filing(AAPL_2024, 2024),
}


class Connection:
    """Only `begin()` is used directly; everything else goes through the patches."""

    def __init__(self) -> None:
        self.transactions = 0

    def begin(self) -> "Connection":
        self.transactions += 1
        return self

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc_info) -> None:
        return None


class Embeddings:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    async def create(self, *, model: str, input: str) -> SimpleNamespace:
        self.requests.append((model, input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.6, 0.8])])


def _refs(document_id: uuid.UUID, *indexes: int) -> list[ChunkRef]:
    return [ChunkRef(document_id, index) for index in indexes]


@pytest.fixture
def calls(monkeypatch) -> dict:
    """Two stored filings, AAPL FY2023 and FY2024, and canned rankings for each."""
    calls: dict = {}

    async def find_filings(connection, keys):
        calls["find_filings"] = list(keys)
        return {key: FILINGS[key] for key in calls["find_filings"] if key in FILINGS}

    async def semantic_search(connection, embedding, document_ids, limit):
        calls["semantic_search"] = (embedding, list(document_ids), limit)
        return {AAPL_2023: _refs(AAPL_2023, 1, 2, 3), AAPL_2024: _refs(AAPL_2024, 3, 9)}

    async def keyword_search(connection, terms, document_ids, limit):
        calls["keyword_search"] = (terms, list(document_ids), limit)
        # FY2024 has no keyword matches at all.
        return {AAPL_2023: _refs(AAPL_2023, 3, 4)}

    async def read_passages(connection, hits):
        calls["read_passages"] = list(hits)
        return {hit: Passage(_chunk(hit), context=()) for hit in calls["read_passages"]}

    monkeypatch.setattr(documents, "find_filings", find_filings)
    monkeypatch.setattr(documents, "read_passages", read_passages)
    monkeypatch.setattr(queries, "semantic_search", semantic_search)
    monkeypatch.setattr(queries, "keyword_search", keyword_search)
    return calls


def _chunk(hit: ChunkRef) -> Chunk:
    return Chunk(
        id=uuid.uuid5(hit.document_id, str(hit.chunk_index)),
        document_id=hit.document_id,
        chunk_index=hit.chunk_index,
        section="Item 7. Management's Discussion and Analysis",
        page="22",
        content=f"chunk {hit.chunk_index}",
        token_count=400,
    )


def _retrieve(slices: list[Slice], k: int = retriever.K) -> list[retriever.SliceResult]:
    client = SimpleNamespace(embeddings=Embeddings())
    return asyncio.run(retriever.retrieve(Connection(), client, QUESTION, slices, k=k))


def _indexes(result: retriever.SliceResult) -> list[tuple[uuid.UUID, int]]:
    return [
        (passage.chunk.document_id, passage.chunk.chunk_index)
        for passage in result.passages
    ]


def test_each_slice_is_searched_in_its_own_filing_and_answered_in_order(calls):
    slices = [Slice("AAPL", 2024), Slice("AAPL", 2020), Slice("AAPL", 2023)]

    fy2024, fy2020, fy2023 = _retrieve(slices)

    assert calls["find_filings"] == slices
    # The searches are filtered to the filings the slices resolved to, and to
    # nothing else: FY2020 is not in the corpus.
    assert sorted(calls["semantic_search"][1]) == [AAPL_2023, AAPL_2024]
    assert sorted(calls["keyword_search"][1]) == [AAPL_2023, AAPL_2024]
    assert (fy2024.slice, fy2024.filing.id) == (Slice("AAPL", 2024), AAPL_2024)
    assert _indexes(fy2024) == [(AAPL_2024, 3), (AAPL_2024, 9)]
    assert (fy2020.filing, fy2020.passages) == (None, [])
    assert {document_id for document_id, _ in _indexes(fy2023)} == {AAPL_2023}


def test_a_filing_s_two_rankings_are_fused_and_cut_to_k(calls):
    (fy2023,) = _retrieve([Slice("AAPL", 2023)], k=3)

    # Chunk 3 is third by distance but also first by keywords, so it leads;
    # 4, only a keyword match, is the one cut.
    assert _indexes(fy2023) == [(AAPL_2023, 3), (AAPL_2023, 1), (AAPL_2023, 2)]
    assert calls["read_passages"] == _refs(AAPL_2023, 3, 1, 2)


def test_the_question_is_embedded_and_or_ed_once_for_every_slice(calls):
    connection, embeddings = Connection(), Embeddings()
    client = SimpleNamespace(embeddings=embeddings)
    slices = [Slice("AAPL", 2023), Slice("AAPL", 2024)]

    asyncio.run(retriever.retrieve(connection, client, QUESTION, slices))

    assert embeddings.requests == [(settings.openai_embedding_model, QUESTION)]
    embedding, _, limit = calls["semantic_search"]
    assert (embedding, limit) == ([0.6, 0.8], retriever.CANDIDATES)
    assert calls["keyword_search"][0] == queries.keyword_query(QUESTION)
    # One transaction: `SET LOCAL` has to outlive the vector search.
    assert connection.transactions == 1
