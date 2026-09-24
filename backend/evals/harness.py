"""Scoring retrieval against expected evidence: the machinery behind `evals.brief`.

A question names the filings to search and, for each one, the evidence an
analyst would need from it: figures and sentences exactly as the filing prints
them. Evidence is text rather than chunk ids, because ids change on every
re-ingest and the filing's words do not.

Each question is searched as written and then once per topic it names, and a
filing's retrieved set is everything those searches return for it. A string
counts as found when a returned passage's chunk contains it, or failing that
the passage's context (the chunks either side, the rest of a split table),
since M4's model reads both. Its rank is the first passage that holds it: at
that `k` or above, retrieval returns it. Every string is also looked up in its
whole filing, so a miss says where the evidence actually is, and a string the
filing does not contain at all — a fixture typo — is reported as that, not as a
retrieval miss.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from string import ascii_lowercase

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import settings
from app.database.engine import create_database_engine
from app.retrieval.retriever import Slice, SliceResult, retrieve

_LOCATE = text("""
    SELECT wanted.document_id, wanted.evidence, c.chunk_index, c.section, c.page,
           c.content
    FROM unnest(CAST(:document_ids AS uuid[]), CAST(:evidence AS text[]))
        AS wanted (document_id, evidence)
    JOIN document_chunks AS c
        ON c.document_id = wanted.document_id AND strpos(c.content, wanted.evidence) > 0
    ORDER BY c.chunk_index
""")


@dataclass(frozen=True)
class Question:
    number: int
    text: str
    # For each filing searched, the strings that must come back with it.
    evidence: dict[Slice, tuple[str, ...]]
    # One further search per topic the question names, worded as an analyst
    # would type it. Searched whole, such a question ranks each topic's
    # passages below the passages that touch several; M4's agent is to
    # search this way.
    topics: tuple[str, ...] = ()
    # The share of its evidence `tests/evals/test_brief.py` holds it to.
    minimum: float = 1.0

    @property
    def searches(self) -> tuple[str, ...]:
        return (self.text, *self.topics)


@dataclass(frozen=True)
class Find:
    # Which search found it: 0 for the question itself, then its topics.
    search: int
    # The first passage of that search, from 1, whose chunk or context holds it.
    rank: int
    in_context: bool


@dataclass(frozen=True)
class SliceScore:
    slice: Slice
    finds: dict[str, Find | None]
    # How many of the strings the question's own search finds, without its topics'.
    found_alone: int
    # Every chunk of the filing that holds each string: "#46 Item 7 p.20–21".
    locations: dict[str, list[str]]
    # What the searches returned for the filing, passages and context together,
    # each chunk counted once.
    chunks: int
    tokens: int


@dataclass(frozen=True)
class QuestionScore:
    question: Question
    slices: list[SliceScore]

    @property
    def found(self) -> int:
        return sum(find is not None for s in self.slices for find in s.finds.values())

    @property
    def total(self) -> int:
        return sum(len(s.finds) for s in self.slices)

    @property
    def recall(self) -> float:
        return self.found / self.total

    @property
    def passed(self) -> bool:
        return self.recall >= self.question.minimum

    @property
    def not_in_filing(self) -> list[tuple[Slice, str]]:
        """Fixture errors: evidence its own filing does not contain."""
        return [
            (s.slice, evidence)
            for s in self.slices
            for evidence, where in s.locations.items()
            if not where
        ]


def contains(text: str, evidence: str) -> bool:
    """Whether `text` holds `evidence` whole: "3,792" is not in "13,792" or "3,792,000"."""
    before = r"(?<!\w)" if evidence[0].isalnum() else ""
    after = r"(?!\w|[.,]\d)" if evidence[-1].isalnum() else ""
    return re.search(before + re.escape(evidence) + after, text) is not None


async def evaluate(questions: Sequence[Question], k: int) -> list[QuestionScore]:
    """Every question through `retrieve`, against the live corpus, scored."""
    engine = create_database_engine()
    try:
        async with (
            AsyncOpenAI(api_key=settings.openai_api_key) as client,
            engine.connect() as connection,
        ):
            return [await _evaluate(connection, client, q, k) for q in questions]
    finally:
        await engine.dispose()


async def _evaluate(
    connection: AsyncConnection, client: AsyncOpenAI, question: Question, k: int
) -> QuestionScore:
    slices = list(question.evidence)
    # One list of per-slice results for each search, in the order of `slices`.
    searches = [
        await retrieve(connection, client, query, slices, k=k)
        for query in question.searches
    ]
    filings = [result.filing for result in searches[0]]
    locations = await _locate(
        connection,
        [
            (filing.id, evidence)
            for wanted, filing in zip(slices, filings, strict=True)
            if filing
            for evidence in question.evidence[wanted]
        ],
    )
    return QuestionScore(
        question,
        [
            _score(
                question.evidence[wanted],
                [results[n] for results in searches],
                locations,
            )
            for n, wanted in enumerate(slices)
        ],
    )


async def _locate(
    connection: AsyncConnection, pairs: list[tuple[uuid.UUID, str]]
) -> dict[tuple[uuid.UUID, str], list[str]]:
    # `strpos` finds candidates; `contains` decides, as it does for passages.
    async with connection.begin():
        result = await connection.execute(
            _LOCATE,
            {
                "document_ids": [document_id for document_id, _ in pairs],
                "evidence": [evidence for _, evidence in pairs],
            },
        )
    locations: dict[tuple[uuid.UUID, str], list[str]] = {}
    for row in result:
        if contains(row.content, row.evidence):
            item = row.section.split(".")[0]
            locations.setdefault((row.document_id, row.evidence), []).append(
                f"#{row.chunk_index} {item} p.{row.page}"
            )
    return locations


def _score(
    evidence: tuple[str, ...],
    results: list[SliceResult],
    locations: dict[tuple[uuid.UUID, str], list[str]],
) -> SliceScore:
    """One slice, scored over what every search returned for it."""
    chunks = {
        chunk.id: chunk
        for result in results
        for passage in result.passages
        for chunk in (passage.chunk, *passage.context)
    }
    filing = results[0].filing
    document_id = filing.id if filing else None
    return SliceScore(
        results[0].slice,
        finds={item: _find(item, results) for item in evidence},
        found_alone=sum(_find(item, results[:1]) is not None for item in evidence),
        locations={item: locations.get((document_id, item), []) for item in evidence},
        chunks=len(chunks),
        tokens=sum(chunk.token_count for chunk in chunks.values()),
    )


def _find(evidence: str, results: list[SliceResult]) -> Find | None:
    """The best rank any search found `evidence` at, the question's own on a tie."""
    finds = []
    for search, result in enumerate(results):
        for rank, passage in enumerate(result.passages, start=1):
            if contains(passage.chunk.content, evidence):
                finds.append(Find(search, rank, in_context=False))
                break
            if any(contains(chunk.content, evidence) for chunk in passage.context):
                finds.append(Find(search, rank, in_context=True))
                break
    return min(finds, key=lambda find: (find.rank, find.search), default=None)


def report(scores: Sequence[QuestionScore], k: int) -> str:
    """Recall per question and per filing; the rank of each find; where each miss is."""
    lines = [
        f"Brief retrieval eval: {k} passages per filing and search, with their context.",
        (
            "#n: passage n of the question's own search holds the string; a#n: of "
            "its first topic's search, and so on; +: that passage's context holds it."
        ),
    ]
    for score in scores:
        question = score.question
        verdict = "ok" if score.passed else f"BELOW {question.minimum:.0%}"
        lines.append(
            f"\nQ{question.number:<2} {score.found:>3}/{score.total:<3} {verdict:<9} "
            f"{_clip(question.text, 84)}"
        )
        for letter, topic in zip(ascii_lowercase, question.topics):
            lines.append(f"    {letter}) {topic}")
        for s in score.slices:
            found = sum(find is not None for find in s.finds.values())
            ranks = " ".join(_rank(find) for find in s.finds.values())
            lines.append(
                f"    {s.slice.ticker:<5} FY{s.slice.fiscal_year}  "
                f"{found}/{len(s.finds)}  {ranks}"
            )
            for evidence, find in s.finds.items():
                where = s.locations[evidence]
                if not where:
                    lines.append(f"        NOT IN THE FILING: {evidence!r}")
                elif find is None:
                    lines.append(
                        f"        missed {_clip(evidence, 60)!r}, in {', '.join(where)}"
                    )

    slices = [s for score in scores for s in score.slices]
    found = sum(score.found for score in scores)
    total = sum(score.total for score in scores)
    alone = sum(s.found_alone for s in slices)
    through_context = sum(
        find.in_context for s in slices for find in s.finds.values() if find
    )
    passed = sum(score.passed for score in scores)
    chunks = sum(s.chunks for s in slices) / len(slices)
    tokens = sum(s.tokens for s in slices) / len(slices)
    lines.append(
        f"\nFound {found} of {total} strings ({found / total:.0%}); the questions' "
        f"own searches alone find {alone}. {through_context} are first reached "
        f"through a passage's context. {passed} of {len(scores)} questions at their "
        f"minimum. Returned per filing: {chunks:.1f} distinct chunks, {tokens:,.0f} "
        f"tokens."
    )
    return "\n".join(lines)


def _rank(find: Find | None) -> str:
    if find is None:
        return "—"
    search = ascii_lowercase[find.search - 1] if find.search else ""
    return f"{search}#{find.rank}{'+' if find.in_context else ''}"


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"
