"""What counts as found, and that the fixture asks the brief's own questions."""

from pathlib import Path

import pytest

from evals.brief import QUESTIONS
from evals.harness import contains

BRIEF = Path(__file__).resolve().parents[3] / "docs" / "client-brief.md"


@pytest.mark.parametrize(
    ("text", "evidence"),
    [
        ("| International | (2,656) | 3,792 |", "3,792"),
        ("| International | 717 | $(924) |", "(924)"),
        ("Data Center revenue was up 124% from a year ago.", "was up 124%"),
        ("as we are in today, we have placed", "as we are in today"),
    ],
)
def test_evidence_is_found_whole(text, evidence):
    assert contains(text, evidence)


@pytest.mark.parametrize(
    ("text", "evidence"),
    [
        # Inside a larger figure, on either side.
        ("| Other | 13,792 |", "3,792"),
        ("revenue of 3,792,000", "3,792"),
        ("up 3,792.5 million", "3,792"),
        # Inside a longer word.
        ("the Azurewide rollout", "Azure"),
    ],
)
def test_evidence_inside_something_larger_is_not(text, evidence):
    assert not contains(text, evidence)


def test_the_questions_are_the_brief_s_own_words():
    brief = BRIEF.read_text(encoding="utf-8")

    assert [question.number for question in QUESTIONS] == list(range(1, 11))
    for question in QUESTIONS:
        assert f"{question.number}. {question.text}\n" in brief


def test_every_filing_searched_expects_some_evidence():
    assert all(
        evidence and all(evidence)
        for question in QUESTIONS
        for evidence in question.evidence.values()
    )
