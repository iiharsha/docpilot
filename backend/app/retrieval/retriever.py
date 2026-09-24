"""A question and the filings it concerns → the passages that answer it, per filing.

Fan-out is the point. One flat top-k over the corpus clusters on the one or two
filings that match best, so a question about five years silently covers two.
`retrieve` instead runs the whole hybrid search once per slice — one company's
filing for one fiscal year — and returns each slice's own passages:

1. embed the question with the model the corpus was embedded with;
2. find each slice's filing;
3. rank every filing's chunks by cosine distance and by full-text match;
4. fuse the two rankings, per filing, with Reciprocal Rank Fusion;
5. read the best `k` with their context.

Which slices a question needs is the caller's call: the eval names them per
question, and M4's `search_filings` tool will choose them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.database import documents
from app.database.documents import Filing, Passage
from app.retrieval import fusion, queries

# Tuned against `evals/brief.py`; architecture.md ("Retrieval Evaluation") has
# the scores behind each value.
#
# Passages returned per slice.
K = 10
# Chunks each search ranks per filing before fusion. Beyond this, keyword
# matches that owe their rank to a question's commonest words start crowding
# out better semantic ones.
CANDIDATES = 20
# Semantic rank counts double. OR-ed terms ranked without IDF reward a chunk
# for repeating any of a question's words, however common.
SEMANTIC_WEIGHT = 2.0
KEYWORD_WEIGHT = 1.0


class Slice(NamedTuple):
    """One filing to search: a company's report for one fiscal year."""

    ticker: str
    fiscal_year: int
    form_type: str = "10-K"


@dataclass(frozen=True)
class SliceResult:
    slice: Slice
    # None when the corpus has no such filing: something to tell the analyst,
    # not an error.
    filing: Filing | None
    # Best first.
    passages: list[Passage]


async def embed_query(client: AsyncOpenAI, query: str) -> list[float]:
    response = await client.embeddings.create(
        model=settings.openai_embedding_model, input=query
    )
    return response.data[0].embedding


async def retrieve(
    connection: AsyncConnection,
    client: AsyncOpenAI,
    query: str,
    slices: Sequence[Slice],
    k: int = K,
) -> list[SliceResult]:
    """`query`'s `k` best passages in each slice's filing, in the order of `slices`.

    Runs in a transaction of its own, which the vector search needs, so
    `connection` must not already be in one.
    """
    embedding = await embed_query(client, query)
    async with connection.begin():
        filings = await documents.find_filings(connection, slices)
        document_ids = [filing.id for filing in filings.values()]
        semantic = await queries.semantic_search(
            connection, embedding, document_ids, CANDIDATES
        )
        keyword = await queries.keyword_search(
            connection, queries.keyword_query(query), document_ids, CANDIDATES
        )
        ranked = {
            document_id: fusion.fuse(
                [semantic.get(document_id, []), keyword.get(document_id, [])],
                weights=(SEMANTIC_WEIGHT, KEYWORD_WEIGHT),
            )[:k]
            for document_id in document_ids
        }
        passages = await documents.read_passages(
            connection, [hit for hits in ranked.values() for hit in hits]
        )

    results = []
    for wanted in slices:
        filing = filings.get(wanted)
        hits = ranked[filing.id] if filing else []
        results.append(SliceResult(wanted, filing, [passages[hit] for hit in hits]))
    return results
