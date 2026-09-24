"""The brief's ten questions against the live corpus, each held to its minimum.

`integration`: needs the database and OpenAI, about a minute, and embeds a few
dozen question-sized texts. `uv run python -m evals.brief` prints the same run
as a report.
"""

import asyncio

import pytest

from app.retrieval.retriever import K
from evals import brief, harness

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def scores() -> dict[int, harness.QuestionScore]:
    return {
        score.question.number: score
        for score in asyncio.run(harness.evaluate(brief.QUESTIONS, K))
    }


def test_every_expected_string_is_in_its_own_filing(scores):
    # Otherwise a typo in the fixture would read as a retrieval miss.
    assert [
        (number, missing)
        for number, score in scores.items()
        for missing in score.not_in_filing
    ] == []


@pytest.mark.parametrize(
    "question", brief.QUESTIONS, ids=lambda question: f"Q{question.number}"
)
def test_the_question_finds_its_evidence(scores, question):
    score = scores[question.number]

    assert score.passed, harness.report([score], K)
