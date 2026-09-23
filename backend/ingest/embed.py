"""Chunk embeddings from the OpenAI API, batched to its per-request limits."""

from collections.abc import Iterator

from openai import OpenAI

from app.database.models.constants import EMBEDDING_DIMENSIONS
from ingest.chunker import Chunk, TokenCounter
from ingest.metadata import Filing

# The embeddings endpoint's limits: inputs and total tokens per request, and
# tokens per input for the text-embedding-3 models.
MAX_INPUTS_PER_REQUEST = 2048
MAX_TOKENS_PER_REQUEST = 300_000
MAX_TOKENS_PER_INPUT = 8191


def embedding_text(filing: Filing, chunk: Chunk) -> str:
    """What is embedded for a chunk: its passage, under a line naming its source.

    "Apple Inc. — 10-K FY2024 — Item 7. …" lets a passage that never names
    its company or year still match a question that does. The line is not part
    of `content`, so full-text search and citations see only the passage.
    """
    source = f"{filing.company_name} — {filing.form_type} FY{filing.fiscal_year} — {chunk.section}"
    return f"{source}\n\n{chunk.content}"


def embed(
    client: OpenAI, model: str, texts: list[str], count_tokens: TokenCounter
) -> list[list[float]]:
    """One vector per text, in order. Every text is checked before the first request."""
    tokens = [count_tokens(text) for text in texts]
    for text, count in zip(texts, tokens, strict=True):
        if not text.strip():
            raise ValueError("refusing to embed an empty text")
        if count > MAX_TOKENS_PER_INPUT:
            raise ValueError(
                f"a text of {count} tokens exceeds the {MAX_TOKENS_PER_INPUT}-token input limit"
            )

    vectors: list[list[float]] = []
    for batch in _batches(texts, tokens):
        response = client.embeddings.create(model=model, input=batch)
        data = sorted(response.data, key=lambda item: item.index)
        if len(data) != len(batch):
            raise RuntimeError(f"asked for {len(batch)} embeddings, got {len(data)}")
        for item in data:
            # Not requested with `dimensions`: a model that answers at another
            # width is a configuration error, and should fail, not be truncated.
            if len(item.embedding) != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    f"{model} returned {len(item.embedding)} dimensions; "
                    f"document_chunks.embedding holds {EMBEDDING_DIMENSIONS}"
                )
        vectors.extend(item.embedding for item in data)
    return vectors


def _batches(texts: list[str], tokens: list[int]) -> Iterator[list[str]]:
    batch: list[str] = []
    batch_tokens = 0
    for text, count in zip(texts, tokens, strict=True):
        if batch and (
            len(batch) == MAX_INPUTS_PER_REQUEST
            or batch_tokens + count > MAX_TOKENS_PER_REQUEST
        ):
            yield batch
            batch, batch_tokens = [], 0
        batch.append(text)
        batch_tokens += count
    if batch:
        yield batch
