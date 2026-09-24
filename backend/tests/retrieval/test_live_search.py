"""The vector search against the live corpus, on the plan that used to break it.

`integration`: needs the database, but not OpenAI — a stored chunk's embedding
stands in for a question's.
"""

import asyncio
import uuid

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text

from app.database.engine import create_database_engine
from app.database.models.constants import EMBEDDING_DIMENSIONS
from app.retrieval import queries
from app.retrieval.retriever import K

pytestmark = pytest.mark.integration


async def _search_on_the_hnsw_index() -> tuple[
    list[uuid.UUID], dict[uuid.UUID, list], str
]:
    engine = create_database_engine()
    try:
        async with engine.connect() as connection, connection.begin():
            document_ids = list(
                (await connection.execute(text("SELECT id FROM source_documents")))
                .scalars()
                .all()
            )
            stored = await connection.execute(
                text("SELECT embedding::text FROM document_chunks LIMIT 1")
            )
            embedding = [float(x) for x in stored.scalar_one().strip("[]").split(",")]
            # Without sorting, the planner has to read the HNSW index, which
            # returns chunks in distance order. Left alone it scans each
            # filing's chunks and sorts them instead.
            await connection.execute(text("SET LOCAL enable_sort = off"))
            parameters = {
                "document_ids": document_ids,
                "embedding": embedding,
                "limit": K,
            }
            plan = await connection.execute(
                text(f"EXPLAIN {queries.SEMANTIC_SEARCH.text}").bindparams(
                    bindparam("embedding", type_=Vector(EMBEDDING_DIMENSIONS))
                ),
                parameters,
            )
            plan_text = "\n".join(plan.scalars())
            ranked = await queries.semantic_search(
                connection, embedding, document_ids, K
            )
    finally:
        await engine.dispose()
    return document_ids, ranked, plan_text


def test_a_filing_filtered_vector_search_returns_k_chunks_for_every_filing():
    document_ids, ranked, plan = asyncio.run(_search_on_the_hnsw_index())

    assert "ix_document_chunks_embedding_hnsw" in plan
    assert len(document_ids) == 25
    # On this plan without an iterative scan, all 25 filings came back short:
    # 40 chunks between them, `hnsw.ef_search`'s default (checked 2026-09-24).
    assert {
        document_id: len(ranked.get(document_id, [])) for document_id in document_ids
    } == {document_id: K for document_id in document_ids}
