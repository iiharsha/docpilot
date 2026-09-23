"""Chunks of real filing pages: where they start and end, which pages they
name, how a large table is split, and the offset rule `verify` enforces."""

import dataclasses
import re

import pytest

from ingest import FilingError, chunker
from ingest.markdown import item_heading, strip_markers

# A table row naming a group: "| North America |  |  |  |".
GROUP_LABEL = re.compile(r"^\| [^|]+ (?:\|  )+\|$", re.MULTILINE)

WITH_ITEMS = [
    "aapl_2024_front.htm",
    "googl_2024_risk_factors.htm",
    "msft_2024_item_7a.htm",
    "msft_2024_part_iii.htm",
]


@pytest.mark.parametrize("fixture", WITH_ITEMS)
def test_every_chunk_is_its_offsets_without_page_markers(
    filing_markdown, count_tokens, fixture
):
    markdown = filing_markdown(fixture)
    chunks = chunker.chunk_markdown(markdown, count_tokens)

    assert chunks
    for chunk in chunks:
        assert chunk.content[chunk.prefix_len :] == strip_markers(
            markdown[chunk.start : chunk.end]
        )
    chunker.verify(markdown, chunks)


def test_chunks_never_cross_an_item(filing_markdown, count_tokens):
    # Three Items share page 101; Item 9C is one line long.
    markdown = filing_markdown("msft_2024_part_iii.htm")
    chunks = chunker.chunk_markdown(markdown, count_tokens)

    assert [chunk.section for chunk in chunks] == [
        "Item 9B. Other Information",
        "Item 9C. Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
        "Item 10. Directors, Executive Officers and Corporate Governance",
    ]
    assert chunks[0].content.endswith("during the three months ended June 30, 2024.")
    assert chunks[1].content == "Not applicable."
    assert chunks[2].content.startswith("A list of our executive officers")
    assert {chunk.page for chunk in chunks} == {"101"}


def test_text_before_the_first_item_is_not_chunked(filing_markdown, count_tokens):
    chunks = chunker.chunk_markdown(
        filing_markdown("aapl_2024_front.htm"), count_tokens
    )

    assert {chunk.section for chunk in chunks} == {"Item 1. Business"}
    assert not any("TABLE OF CONTENTS" in chunk.content for chunk in chunks)


def test_a_chunk_names_the_pages_it_runs_across(filing_markdown, count_tokens):
    chunks = chunker.chunk_markdown(
        filing_markdown("googl_2024_risk_factors.htm"), count_tokens
    )
    across = next(
        chunk for chunk in chunks if "or more effective monetization)" in chunk.content
    )

    assert across.page == "10–11"
    assert chunks[-1].page == "11"


def test_consecutive_chunks_overlap_by_whole_sentences(filing_markdown, count_tokens):
    markdown = filing_markdown("googl_2024_risk_factors.htm")
    first, second = chunker.chunk_markdown(markdown, count_tokens)[:2]

    overlap = strip_markers(markdown[second.start : first.end])
    assert second.start < first.end
    assert first.content.endswith(overlap)
    assert second.content.startswith(overlap)
    # It opens a sentence, and the text before it closes one.
    assert overlap[0].isupper()
    assert markdown[: second.start].rstrip()[-1] in ".!?"


def test_a_large_table_repeats_its_header_and_group_in_every_piece(
    filing_markdown, count_tokens, monkeypatch
):
    # Amazon's segment table fits a real chunk whole; at these sizes it is split.
    monkeypatch.setattr(chunker, "TARGET_TOKENS", 120)
    monkeypatch.setattr(chunker, "MAX_TOKENS", 160)
    monkeypatch.setattr(chunker, "MIN_TOKENS", 60)
    markdown = (
        item_heading("8", "Financial Statements and Supplementary Data")
        + "\n\n"
        + filing_markdown("amzn_2024_segments.htm")
    )
    chunks = chunker.chunk_markdown(markdown, count_tokens)
    pieces = [chunk for chunk in chunks if chunk.table_part]
    head = (
        "Information on reportable segments and reconciliation to consolidated net "
        "income (loss) is as follows (in millions):\n"
        "|  | Year Ended December 31, 2022 | Year Ended December 31, 2023 "
        "| Year Ended December 31, 2024 |\n"
        "| --- | --- | --- | --- |\n"
    )

    assert len(pieces) > 2
    assert [chunk.table_part for chunk in pieces] == [
        (n, len(pieces)) for n in range(1, len(pieces) + 1)
    ]
    assert pieces[0].prefix_len == 0
    assert head in pieces[0].content
    # Each later piece opens with the header, then the group its first rows
    # belong to — without "Consolidated" above it, "(18,184)" says nothing.
    carried = 0
    for piece in pieces[1:]:
        prefix, body = (
            piece.content[: piece.prefix_len],
            piece.content[piece.prefix_len :],
        )
        groups = GROUP_LABEL.findall(markdown, 0, piece.start)
        assert prefix.startswith(head)
        if not GROUP_LABEL.match(body):
            assert prefix.endswith(groups[-1] + "\n")
            carried += 1
    assert carried
    chunker.verify(markdown, chunks)


def test_chunking_is_deterministic(filing_markdown, count_tokens):
    markdown = filing_markdown("googl_2024_risk_factors.htm")

    assert chunker.chunk_markdown(markdown, count_tokens) == chunker.chunk_markdown(
        markdown, count_tokens
    )


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"section": "Item 9B. Other Information"}, "is not inside"),
        (
            {"content": "A passage the filing does not contain."},
            "does not match its offsets",
        ),
    ],
)
def test_verify_refuses_a_chunk_that_misstates_itself(
    filing_markdown, count_tokens, change, error
):
    markdown = filing_markdown("msft_2024_part_iii.htm")
    chunks = chunker.chunk_markdown(markdown, count_tokens)
    chunks[-1] = dataclasses.replace(chunks[-1], **change)

    with pytest.raises(FilingError, match=error):
        chunker.verify(markdown, chunks)


def test_verify_refuses_a_chunk_that_runs_into_the_next_item(
    filing_markdown, count_tokens
):
    markdown = filing_markdown("msft_2024_part_iii.htm")
    chunks = chunker.chunk_markdown(markdown, count_tokens)
    end = chunks[2].start
    stretched = dataclasses.replace(
        chunks[0], end=end, content=strip_markers(markdown[chunks[0].start : end])
    )

    with pytest.raises(FilingError, match="crosses into"):
        chunker.verify(markdown, [stretched])
