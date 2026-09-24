"""The two ranked searches hybrid retrieval fuses, each bounded per filing.

Both take the filings to search as document ids and return, for each one, its
`limit` best chunks in rank order. A lateral join runs the bounded search once
per filing inside one statement, so fanning a question out over twenty filings
still costs one round trip per search.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.database.documents import ChunkRef
from app.database.models.constants import EMBEDDING_DIMENSIONS

# Runs of letters and digits: the words of a question, split on everything
# else, including the slashes that Postgres's parser would read as a file path.
_TERM = re.compile(r"[^\W_]+")

SEMANTIC_SEARCH = text("""
    SELECT hit.document_id, hit.chunk_index, hit.table_part, hit.table_parts
    FROM unnest(CAST(:document_ids AS uuid[])) AS filing (id)
    CROSS JOIN LATERAL (
        SELECT c.document_id, c.chunk_index,
               (c.metadata->>'table_part')::integer AS table_part,
               (c.metadata->>'table_parts')::integer AS table_parts,
               c.embedding <=> CAST(:embedding AS vector) AS distance
        FROM document_chunks AS c
        WHERE c.document_id = filing.id
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    ) AS hit
    ORDER BY hit.document_id, hit.distance, hit.chunk_index
""").bindparams(bindparam("embedding", type_=Vector(EMBEDDING_DIMENSIONS)))

KEYWORD_SEARCH = text("""
    SELECT hit.document_id, hit.chunk_index, hit.table_part, hit.table_parts
    FROM unnest(CAST(:document_ids AS uuid[])) AS filing (id)
    CROSS JOIN LATERAL (
        SELECT c.document_id, c.chunk_index,
               (c.metadata->>'table_part')::integer AS table_part,
               (c.metadata->>'table_parts')::integer AS table_parts,
               ts_rank_cd(c.search_vector, query.terms) AS rank
        FROM document_chunks AS c, to_tsquery('english', :terms) AS query (terms)
        WHERE c.document_id = filing.id AND c.search_vector @@ query.terms
        ORDER BY rank DESC, c.chunk_index
        LIMIT :limit
    ) AS hit
    ORDER BY hit.document_id, hit.rank DESC, hit.chunk_index
""")


def keyword_query(question: str) -> str | None:
    """`question`'s words OR-ed together for `to_tsquery`: "revenue | mix | iphone".

    `plainto_tsquery` and `websearch_to_tsquery` both require every word, and
    no passage contains every word of a whole question: brief question 1
    matches nothing either way. OR-ed, any word matches and `ts_rank_cd`
    orders by how densely they occur. Stemming and stop words are left to the
    `english` configuration the index was built with. None when there are no
    words at all.
    """
    terms = dict.fromkeys(_TERM.findall(question.lower()))
    return " | ".join(terms) or None


async def semantic_search(
    connection: AsyncConnection,
    embedding: Sequence[float],
    document_ids: Sequence[uuid.UUID],
    limit: int,
) -> dict[uuid.UUID, list[ChunkRef]]:
    """Each filing's `limit` chunks nearest `embedding`, by cosine distance.

    Must run inside a transaction. The HNSW index filters after it searches:
    a plan that scans it for one filing's chunks finds the 40 nearest in the
    whole corpus (`hnsw.ef_search`) and keeps that filing's few, often none.
    With an iterative scan it keeps going until it has `limit`. Left to itself the
    planner currently scans a filing's chunks exactly instead, where the
    setting changes nothing — but that is a plan choice, not a guarantee.
    `relaxed_order` can return near-ties slightly out of order, which the
    outer `ORDER BY` puts right. `SET LOCAL` lasts until the transaction ends.
    """
    await connection.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    result = await connection.execute(
        SEMANTIC_SEARCH,
        {"document_ids": list(document_ids), "embedding": embedding, "limit": limit},
    )
    return _by_document(result)


async def keyword_search(
    connection: AsyncConnection,
    terms: str | None,
    document_ids: Sequence[uuid.UUID],
    limit: int,
) -> dict[uuid.UUID, list[ChunkRef]]:
    """Each filing's `limit` chunks that best match `terms`, from `keyword_query`.

    A filing where no chunk contains any of the terms is left out.
    """
    if terms is None:
        return {}
    result = await connection.execute(
        KEYWORD_SEARCH,
        {"document_ids": list(document_ids), "terms": terms, "limit": limit},
    )
    return _by_document(result)


def _by_document(rows: Iterable[Any]) -> dict[uuid.UUID, list[ChunkRef]]:
    ranked: dict[uuid.UUID, list[ChunkRef]] = {}
    for row in rows:
        table_part = (row.table_part, row.table_parts) if row.table_part else None
        ranked.setdefault(row.document_id, []).append(
            ChunkRef(row.document_id, row.chunk_index, table_part)
        )
    return ranked
