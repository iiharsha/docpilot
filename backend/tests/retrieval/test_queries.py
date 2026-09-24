"""The keyword query built from a question, and what the two searches send.

The SQL itself is exercised against the live corpus by the `integration` tests
in `tests/evals/`; here, statements are recorded rather than run.
"""

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.database.documents import ChunkRef
from app.retrieval import queries


class RecordingConnection:
    """Stands in for an `AsyncConnection` far enough to record statements."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, object]] = []

    async def execute(self, statement, parameters=None) -> list[SimpleNamespace]:
        self.statements.append((str(statement), parameters))
        return self.rows


def _row(document_id: uuid.UUID, chunk_index: int, table_part=None) -> SimpleNamespace:
    part, parts = table_part or (None, None)
    return SimpleNamespace(
        document_id=document_id,
        chunk_index=chunk_index,
        table_part=part,
        table_parts=parts,
    )


@pytest.mark.parametrize(
    ("question", "terms"),
    [
        (
            "How did Apple's iPhone revenue change?",
            "how | did | apple | s | iphone | revenue | change",
        ),
        # Postgres would read the whole thing as one file-path lexeme.
        ("subscriptions/platforms/devices", "subscriptions | platforms | devices"),
        ("Across the 2021–2025 10-Ks", "across | the | 2021 | 2025 | 10 | ks"),
        ("AI, and AI/cloud", "ai | and | cloud"),
        # `to_tsquery` operators never reach it.
        ("a & b | !c (d):*", "a | b | c | d"),
    ],
)
def test_a_question_becomes_its_words_or_ed_together(question, terms):
    assert queries.keyword_query(question) == terms


@pytest.mark.parametrize("question", ["", " ?! — "])
def test_a_question_without_words_has_no_keyword_query(question):
    assert queries.keyword_query(question) is None


def test_the_vector_search_turns_on_iterative_scan_before_it_runs():
    document_id = uuid.uuid4()
    connection = RecordingConnection([_row(document_id, 7), _row(document_id, 3)])

    ranked = asyncio.run(
        queries.semantic_search(connection, [0.1, 0.2], [document_id], limit=2)
    )

    (setting, _), (search, parameters) = connection.statements
    # `SET LOCAL`, so the caller's transaction is what bounds it.
    assert setting == "SET LOCAL hnsw.iterative_scan = relaxed_order"
    assert search == str(queries.SEMANTIC_SEARCH)
    assert parameters == {
        "document_ids": [document_id],
        "embedding": [0.1, 0.2],
        "limit": 2,
    }
    assert ranked == {document_id: [ChunkRef(document_id, 7), ChunkRef(document_id, 3)]}


def test_search_rows_come_back_ranked_per_filing_with_their_table_parts():
    first, second = uuid.uuid4(), uuid.uuid4()
    connection = RecordingConnection(
        [_row(first, 40, table_part=(2, 3)), _row(first, 12), _row(second, 5)]
    )

    ranked = asyncio.run(
        queries.keyword_search(connection, "aws | income", [first, second], limit=2)
    )

    assert connection.statements == [
        (
            str(queries.KEYWORD_SEARCH),
            {"document_ids": [first, second], "terms": "aws | income", "limit": 2},
        )
    ]
    assert ranked == {
        first: [ChunkRef(first, 40, (2, 3)), ChunkRef(first, 12)],
        second: [ChunkRef(second, 5)],
    }


def test_no_keyword_query_searches_nothing():
    connection = RecordingConnection([])

    ranked = asyncio.run(queries.keyword_search(connection, None, [uuid.uuid4()], 5))

    assert ranked == {}
    assert connection.statements == []
