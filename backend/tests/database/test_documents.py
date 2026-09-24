"""Corpus reads: which filing a key finds, and what a hit is read with.

Like `test_store.py`, the connection is a stand-in: here it serves a filing's
chunks from memory by (document_id, chunk_index), which is all `read_passages`
asks Postgres for.
"""

import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

from app.database import documents
from app.database.documents import ChunkRef

DOCUMENT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
# Chunks 6–9 are one table, split in four.
TABLE_PARTS = {6: (1, 4), 7: (2, 4), 8: (3, 4), 9: (4, 4)}
LAST_CHUNK = 11


class ChunkStore:
    """One filing's chunks, served by (document_id, chunk_index) like `_CHUNKS`."""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    async def execute(self, statement, parameters) -> list[SimpleNamespace]:
        self.requests.append(parameters)
        positions = zip(
            parameters["document_ids"], parameters["chunk_indexes"], strict=True
        )
        return [
            self._row(index)
            for document_id, index in positions
            if document_id == DOCUMENT_ID and 0 <= index <= LAST_CHUNK
        ]

    def _row(self, index: int) -> SimpleNamespace:
        part, parts = TABLE_PARTS.get(index, (None, None))
        return SimpleNamespace(
            id=uuid.uuid5(DOCUMENT_ID, str(index)),
            document_id=DOCUMENT_ID,
            chunk_index=index,
            section="Item 8. Financial Statements and Supplementary Data",
            page=str(60 + index),
            content=f"chunk {index}",
            token_count=400 + index,
            table_part=part,
            table_parts=parts,
        )


def _hit(index: int) -> ChunkRef:
    return ChunkRef(DOCUMENT_ID, index, TABLE_PARTS.get(index))


def _read(*hits: ChunkRef) -> tuple[dict, ChunkStore]:
    store = ChunkStore()
    return asyncio.run(documents.read_passages(store, hits)), store


def _context(passage: documents.Passage) -> list[int]:
    return [chunk.chunk_index for chunk in passage.context]


def test_a_hit_is_read_with_the_chunk_either_side_in_filing_order():
    passages, _ = _read(_hit(2))

    passage = passages[_hit(2)]
    assert (passage.chunk.content, passage.chunk.page) == ("chunk 2", "62")
    assert passage.chunk.token_count == 402
    assert _context(passage) == [1, 3]


def test_the_first_and_last_chunks_have_one_neighbour():
    passages, _ = _read(_hit(0), _hit(LAST_CHUNK))

    assert _context(passages[_hit(0)]) == [1]
    assert _context(passages[_hit(LAST_CHUNK)]) == [LAST_CHUNK - 1]


def test_a_piece_of_a_split_table_is_read_with_every_other_piece():
    passages, _ = _read(_hit(8))

    # Piece 3 of 4: pieces 1, 2 and 4 are 6, 7 and 9; 7 and 9 are also its
    # neighbours. What precedes the table is left to the first piece's chunk.
    assert _context(passages[_hit(8)]) == [6, 7, 9]
    assert passages[_hit(8)].chunk.table_part == (3, 4)


def test_the_first_piece_of_a_split_table_keeps_the_chunk_before_it():
    passages, _ = _read(_hit(6))

    assert _context(passages[_hit(6)]) == [5, 7, 8, 9]


def test_the_last_piece_of_a_split_table_keeps_the_chunk_after_it():
    passages, _ = _read(_hit(9))

    assert _context(passages[_hit(9)]) == [6, 7, 8, 10]


def test_overlapping_hits_share_one_query_and_each_position_is_read_once():
    passages, store = _read(_hit(2), _hit(3))

    (request,) = store.requests
    assert request["chunk_indexes"] == [1, 2, 3, 4]
    assert request["document_ids"] == [DOCUMENT_ID] * 4
    # Each hit still gets its own context, including the other hit.
    assert _context(passages[_hit(2)]) == [1, 3]
    assert _context(passages[_hit(3)]) == [2, 4]


class FilingStore:
    """Answers `_FILINGS` from a fixed set of stored filings."""

    def __init__(self, stored: list[tuple[str, int, str]]) -> None:
        self.stored = stored
        self.requests: list[dict] = []

    async def execute(self, statement, parameters) -> list[SimpleNamespace]:
        self.requests.append(parameters)
        keys = zip(
            parameters["tickers"],
            parameters["fiscal_years"],
            parameters["form_types"],
            strict=True,
        )
        return [_filing_row(*key) for key in keys if key in self.stored]


def _filing_row(ticker: str, fiscal_year: int, form_type: str) -> SimpleNamespace:
    return SimpleNamespace(
        _mapping={
            "id": uuid.uuid5(DOCUMENT_ID, f"{ticker}{fiscal_year}{form_type}"),
            "ticker": ticker,
            "company_name": f"{ticker} Inc.",
            "form_type": form_type,
            "fiscal_year": fiscal_year,
            "period_end_date": date(fiscal_year, 12, 31),
            "filing_date": date(fiscal_year + 1, 2, 1),
            "accession_number": f"0000000000-{fiscal_year % 100}-000001",
            "source_url": "https://www.sec.gov/",
        }
    )


def test_filings_are_looked_up_by_ticker_year_and_form_together():
    store = FilingStore([("AAPL", 2024, "10-K"), ("MSFT", 2021, "10-K")])

    filings = asyncio.run(
        documents.find_filings(
            store,
            [("AAPL", 2024, "10-K"), ("MSFT", 2021, "10-K"), ("AAPL", 2019, "10-K")],
        )
    )

    # Parallel arrays, so AAPL 2024 and MSFT 2021 never become MSFT 2024.
    assert store.requests == [
        {
            "tickers": ["AAPL", "MSFT", "AAPL"],
            "fiscal_years": [2024, 2021, 2019],
            "form_types": ["10-K", "10-K", "10-K"],
        }
    ]
    assert set(filings) == {("AAPL", 2024, "10-K"), ("MSFT", 2021, "10-K")}
    assert filings["AAPL", 2024, "10-K"].company_name == "AAPL Inc."
