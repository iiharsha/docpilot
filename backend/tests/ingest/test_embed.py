"""Embedding requests: what is sent, how it is batched, and what is accepted back."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.database.models.constants import EMBEDDING_DIMENSIONS
from ingest import embed
from ingest.chunker import Chunk
from ingest.metadata import Filing


class FakeEmbeddings:
    """Answers like the embeddings endpoint — in reverse order, which the API
    does not promise not to do — and records every request."""

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.requests: list[list[str]] = []
        self.dimensions = dimensions

    def create(self, *, model: str, input: list[str]) -> SimpleNamespace:
        self.requests.append(list(input))
        data = [
            SimpleNamespace(index=index, embedding=[float(len(text))] * self.dimensions)
            for index, text in enumerate(input)
        ]
        return SimpleNamespace(data=data[::-1])


def _client(embeddings: FakeEmbeddings) -> SimpleNamespace:
    return SimpleNamespace(embeddings=embeddings)


def test_vectors_come_back_in_the_order_of_the_texts(count_tokens):
    vectors = embed.embed(
        _client(FakeEmbeddings()), "model", ["a", "bb", "ccc"], count_tokens
    )

    assert [vector[0] for vector in vectors] == [1.0, 2.0, 3.0]


def test_requests_stay_under_the_input_and_token_limits(count_tokens, monkeypatch):
    monkeypatch.setattr(embed, "MAX_INPUTS_PER_REQUEST", 3)
    monkeypatch.setattr(embed, "MAX_TOKENS_PER_REQUEST", 6)
    embeddings = FakeEmbeddings()
    texts = [
        "one two three four",
        "five six seven",
        "eight",
        "nine",
        "ten",
        "eleven twelve",
    ]

    embed.embed(_client(embeddings), "model", texts, count_tokens)

    # 4 + 3 words is over the token limit; the next three reach the input limit.
    assert embeddings.requests == [texts[:1], texts[1:4], texts[4:]]


def test_a_vector_of_another_width_is_refused(count_tokens):
    with pytest.raises(RuntimeError, match="returned 3072 dimensions"):
        embed.embed(
            _client(FakeEmbeddings(dimensions=3072)), "model", ["text"], count_tokens
        )


@pytest.mark.parametrize(
    "texts", [["text", "  "], ["text", "word " * (embed.MAX_TOKENS_PER_INPUT + 1)]]
)
def test_a_text_the_endpoint_would_reject_is_refused_before_any_request(
    count_tokens, texts
):
    embeddings = FakeEmbeddings()

    with pytest.raises(ValueError, match="empty|input limit"):
        embed.embed(_client(embeddings), "model", texts, count_tokens)
    assert embeddings.requests == []


def test_the_embedded_text_names_the_filing_but_the_chunk_does_not():
    filing = Filing(
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        form_type="10-K",
        accession_number="0000320193-24-000123",
        filing_date=date(2024, 11, 1),
        period_end_date=date(2024, 9, 28),
        fiscal_year=2024,
        source_url="https://www.sec.gov/",
    )
    chunk = Chunk(
        section="Item 7. Management's Discussion and Analysis of Financial Condition and "
        "Results of Operations",
        page="23",
        content="iPhone net sales were relatively flat during 2024 compared to 2023.",
        prefix_len=0,
        start=0,
        end=68,
        token_count=11,
        chunk_type="text",
    )

    assert embed.embedding_text(filing, chunk) == (
        "Apple Inc. — 10-K FY2024 — Item 7. Management's Discussion and Analysis of "
        "Financial Condition and Results of Operations\n\n"
        "iPhone net sales were relatively flat during 2024 compared to 2023."
    )
