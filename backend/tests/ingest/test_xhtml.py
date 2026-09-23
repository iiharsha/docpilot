"""XHTML → Markdown on real filing pages: what is text, what is page furniture,
and where each Item begins."""

import pytest

from ingest import FilingError, xhtml
from ingest.markdown import ITEM_HEADING, strip_markers


def _blocks(markdown: str) -> list[str]:
    return markdown.split("\n\n")


def test_xbrl_tags_are_transparent(filing_markdown):
    # Every figure in Amazon's segment table sits inside an ix:nonFraction.
    markdown = filing_markdown("amzn_2024_segments.htm")

    assert "| Operating income (loss) | $(7,746) | $(2,656) | $3,792 |" in markdown


def test_the_hidden_xbrl_header_stays_out_of_the_text(filing_markdown):
    # dei:EntityCentralIndexKey appears only in Apple's hidden ix:header.
    assert "0000320193" not in filing_markdown("aapl_2024_front.htm")


def test_each_footer_becomes_its_page_label(filing_root, filing_markdown):
    pages = xhtml.read_pages(filing_root("aapl_2024_front.htm"))
    markdown = filing_markdown("aapl_2024_front.htm")

    # The cover page and the table of contents print no number.
    assert [page.label for page in pages] == [None, None, "1"]
    assert markdown.count("<!-- page -->") == 2
    assert "<!-- page 1 -->" in markdown
    assert "Apple Inc. | 2024 Form 10-K" not in markdown


def test_a_label_printed_with_a_period_is_read(filing_root):
    # Alphabet's footers read "10.".
    pages = xhtml.read_pages(filing_root("googl_2024_risk_factors.htm"))

    assert [page.label for page in pages] == ["10", "11"]


@pytest.mark.parametrize(
    ("fixture", "header"),
    [
        # A link back to the contents, beside the company name in a layout table.
        ("googl_2024_risk_factors.htm", "Table of Contents Alphabet Inc."),
        ("msft_2024_item_7a.htm", "PART II"),
        ("msft_2024_item_7a.htm", "Item 7A"),
        ("msft_2024_part_iii.htm", "PART II, III"),
        ("msft_2024_part_iii.htm", "Item 9B, 9C, 10"),
        (
            "nvda_2024_income_taxes.htm",
            "Notes to the Consolidated Financial Statements",
        ),
        ("nvda_2024_income_taxes.htm", "(Continued)"),
    ],
)
def test_running_headers_are_removed(filing_markdown, fixture, header):
    assert header not in _blocks(filing_markdown(fixture))


def test_a_paragraph_cut_by_a_page_break_is_rejoined(filing_markdown):
    markdown = filing_markdown("googl_2024_risk_factors.htm")

    # The marker stays exactly where page 11 begins, inside the sentence.
    assert "or more effective <!-- page 11 --> monetization) than their" in markdown
    assert "or more effective monetization) than their" in strip_markers(markdown)


def test_a_bullet_that_opens_a_page_stays_a_bullet():
    # Alphabet's revenue list breaks across pages 29 and 30 after "…; and".
    pages = [
        xhtml.Page(
            "29", ["- Google Search & other, which includes revenues from …; and"]
        ),
        xhtml.Page("30", ["- Google Network, which includes revenues generated on …"]),
    ]

    assert _blocks(xhtml.render(pages).rstrip("\n")) == [
        "<!-- page 29 -->",
        "- Google Search & other, which includes revenues from …; and",
        "<!-- page 30 -->",
        "- Google Network, which includes revenues generated on …",
    ]


def test_a_table_of_contents_is_not_read_as_headings(filing_markdown):
    # Apple's contents page lists every Item; only the body's Item 1 heads a section.
    markdown = filing_markdown("aapl_2024_front.htm")

    assert [match.group(1) for match in ITEM_HEADING.finditer(markdown)] == [
        "Item 1. Business"
    ]
    assert markdown.index("<!-- page 1 -->") < markdown.index("## Item 1. Business")


def test_a_running_header_is_not_read_as_a_heading(filing_markdown):
    # Page 101 opens "PART II, III / Item 9B, 9C, 10"; each Item starts at its
    # own heading below that.
    markdown = filing_markdown("msft_2024_part_iii.htm")

    assert [match.group(1) for match in ITEM_HEADING.finditer(markdown)] == [
        "Item 9B. Other Information",
        "Item 9C. Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
        "Item 10. Directors, Executive Officers and Corporate Governance",
    ]
    assert markdown.startswith("<!-- page 101 -->\n\n## Item 9B. Other Information\n\n")


def test_headings_are_normalized(filing_markdown):
    # Alphabet prints "ITEM 1A.RISK FACTORS", Microsoft "ITEM 7A. QUANTITATIVE …".
    assert "## Item 1A. Risk Factors" in filing_markdown("googl_2024_risk_factors.htm")
    assert "## Item 7A. Quantitative and Qualitative Disclosures About Market Risk" in (
        filing_markdown("msft_2024_item_7a.htm")
    )


def test_only_headings_that_advance_the_sequence_are_accepted():
    blocks = [
        # A table of contents laid out as text, not as a table.
        "Item 1. Business",
        "Item 1A. Risk Factors",
        "Item 7. Management's Discussion and Analysis",
        # The body restarts the sequence.
        "Item 1. Business",
        "Item 1A. Risk Factors",
        # A cross-reference, a running header and a sentence.
        "Item 1A. Risk Factors",
        "Item 7",
        "Item 7A of Part II describes our market risk.",
        "ITEM 7.MANAGEMENT'S DISCUSSION AND ANALYSIS",
    ]

    assert xhtml.find_items(blocks) == {3: "1", 4: "1A", 8: "7"}


def test_item_6_keeps_the_title_it_had_before_2021():
    page = xhtml.Page("22", ["ITEM 6. SELECTED FINANCIAL DATA", "Not applicable."])

    assert "## Item 6. Selected Financial Data" in xhtml.render([page])


def test_a_filing_missing_items_is_refused(filing_root):
    with pytest.raises(FilingError, match="no heading found for Item 1, 1A"):
        xhtml.to_markdown(filing_root("aapl_2024_net_sales.htm"))


def test_a_filing_whose_pages_print_no_labels_is_refused(filing_root):
    with pytest.raises(FilingError, match="only 1 of 3 pages"):
        xhtml.to_markdown(filing_root("aapl_2024_front.htm"))


@pytest.mark.parametrize(
    "labels", [["10", "11", "3"], ["7", "7"], ["F-1", "56", "F-2"]]
)
def test_page_labels_that_do_not_increase_are_refused(labels):
    with pytest.raises(FilingError, match="follows"):
        xhtml.check_page_labels(labels)


def test_page_labels_may_start_a_new_sequence():
    xhtml.check_page_labels(["55", "56", "F-1", "F-2"])


def test_conversion_is_deterministic(filing_markdown):
    assert filing_markdown("googl_2024_risk_factors.htm") == filing_markdown(
        "googl_2024_risk_factors.htm"
    )
