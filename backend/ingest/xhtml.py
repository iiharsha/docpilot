"""EDGAR inline-XBRL 10-K → the normalized Markdown described in `ingest.markdown`.

EDGAR only accepts inline-XBRL filings that are well-formed XHTML, so the
stdlib parser reads every one. The body is walked in document order:

- `ix:*` elements are transparent. Every figure in the financial statements
  sits inside an `ix:nonFraction`; skipping them would drop all the numbers.
- `display:none` elements are skipped, as a browser skips them — Workiva hides
  whole table columns this way. The text after one (its `.tail`) belongs to
  the parent, and is kept.
- `page-break-*` and `break-*: page` styles end a printed page.

Each page then loses its furniture: the footer, whose last token is the page
label the filing prints, and running headers ("Table of Contents", Microsoft's
"PART II / Item 7"). Only then are Item headings looked for, so a running
header can never be mistaken for one.

Both heuristics are checked on every filing. One that fails raises
`FilingError`: sections or pages that are silently wrong would still produce
confident, well-cited answers.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from itertools import pairwise

from ingest import FilingError, tables
from ingest.markdown import ITEM_HEADING, item_heading, page_marker
from ingest.tables import Cell

# Form 10-K's Items, in order, with the titles emitted as their headings.
# Filers word and case them differently ("ITEM 1.BUSINESS"); citations should
# not.
ITEM_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity, Related Stockholder Matters and "
    "Issuer Purchases of Equity Securities",
    "6": "[Reserved]",
    "7": "Management's Discussion and Analysis of Financial Condition and Results "
    "of Operations",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants on Accounting and "
    "Financial Disclosure",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership of Certain Beneficial Owners and Management and "
    "Related Stockholder Matters",
    "13": "Certain Relationships and Related Transactions, and Director Independence",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}
ITEMS = list(ITEM_TITLES)
# Newer than some filings in the corpus: 1C is required for fiscal years ending
# from December 2023, 9C for reports filed from early 2022.
OPTIONAL_ITEMS = {"1C", "9C"}

# Share of a filing's pages that must print a label. The cover page and the
# table of contents usually don't; a body page without one means the footer
# was not recognized.
MIN_LABELED_PAGES = 0.9

_BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "center", "dd", "div", "dl",
    "dt", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
    "tr", "ul",
}  # fmt: skip
_HIDDEN = re.compile(r"display\s*:\s*none", re.IGNORECASE)
# Microsoft's list items are divs styled inline; they are not their own blocks.
_INLINE = re.compile(r"display\s*:\s*inline", re.IGNORECASE)
_BREAK_BEFORE = re.compile(r"break-before\s*:\s*(?:always|page)", re.IGNORECASE)
_BREAK_AFTER = re.compile(r"break-after\s*:\s*(?:always|page)", re.IGNORECASE)

# "23", "F-12", "II-3". Alphabet prints "23." and Apple
# "Apple Inc. | 2024 Form 10-K | 23", so the label is the footer's last token.
_PAGE_LABEL = re.compile(r"(?:[A-Z]{1,3}-)?\d{1,3}")
_FOOTER_MAX_LENGTH = 80
_RUNNING_HEADER = re.compile(
    # A link back to the contents; Alphabet's comes with the company name.
    r"table of contents(?: .{1,40})?"
    # Microsoft's two header lines: "PART II" or "PART II, III", then "Item 7"
    # or "Item 9B, 9C, 10". Real headings always carry a period and a title.
    r"|part [ivx]{1,4}(?:(?:, | and | & )[ivx]{1,4})*"
    r"|item \d{1,2}[a-c]?(?:(?:, | and | & )\d{1,2}[a-c]?)*",
    re.IGNORECASE,
)
# NVIDIA repeats its statement titles above each page of its notes, then
# "(Continued)". The notes' first page, which says no "(Continued)", keeps them.
_CONTINUED = re.compile(r"\(continued\)", re.IGNORECASE)
_CONTINUED_HEADER_MAX_LINES = 4
# The Items carry the structure; the Part lines around them add nothing. Nor
# does the rule Amazon draws between a table and its footnotes, which would
# otherwise keep the footnotes out of the table's block.
_PART_LINE = re.compile(
    r"part [ivx]{1,4}(?:(?:, | and | & )[ivx]{1,4})*\.?", re.IGNORECASE
)
_RULE_LINE = re.compile(r"_{3,}")

_ITEM_CANDIDATE = re.compile(
    r"item\s+(\d{1,2}[a-c]?)(?![a-z\d])(\s*[.:—–-])?\s*(.*)", re.IGNORECASE
)
_TITLE_START = re.compile(r"[A-Z\[(\"'“‘]")
# Item 6 was "Selected Financial Data" until the SEC removed it in 2021; the
# oldest filings in the corpus still print it.
_SELECTED_FINANCIAL_DATA = re.compile(r"selected financial data", re.IGNORECASE)
_HEADING_MAX_LENGTH = 200
_BULLET = re.compile(r"[•●▪◦‣∙]\s*")
_FOOTNOTE = re.compile(r"\(\d{1,2}\)|\([a-z]\)|\*{1,3}|[¹²³⁴⁵⁶⁷⁸⁹]")
# A paragraph that ends without this was cut by the page break when the next
# page carries on in lower case, or when it stops on a lower-case word or a
# comma ("… aftermarket sales of our" / "GPUs, which …"). Headings end on a
# capital, so one at the foot of a page stays separate.
_COMPLETE = re.compile(r"[.!?:;][\"'”’)\]]*$")
_CUT_OFF = re.compile(r"[a-z,]$")


@dataclass(frozen=True)
class _PageBreak:
    pass


@dataclass(frozen=True)
class _Table:
    rows: list[list[Cell]]


@dataclass(frozen=True)
class DataTable:
    """A data table, already rendered as its Markdown block."""

    markdown: str


@dataclass(frozen=True)
class Page:
    """One printed page: its footer's label, and its content in order.

    Blocks are paragraph text (`str`) or `DataTable`s.
    """

    label: str | None
    blocks: list[str | DataTable]


@dataclass(frozen=True)
class _Marker:
    label: str | None


@dataclass(frozen=True)
class _Heading:
    item: str
    title: str


def to_markdown(root: ET.Element) -> str:
    """The filing as Markdown, or `FilingError` if its pages or Items fail a check."""
    pages = read_pages(root)
    check_page_labels([page.label for page in pages])
    markdown = render(pages)
    check_items(markdown)
    return markdown


def read_pages(root: ET.Element) -> list[Page]:
    """The filing's printed pages, footers and running headers removed."""
    reader = _Reader()
    reader.read(_body(root))
    pages = [_page(blocks) for blocks in _split_pages(_convert(reader.blocks))]
    return [page for page in pages if page.blocks]


def render(pages: list[Page]) -> str:
    """Pages as Markdown, with their Item headings. `to_markdown` adds the checks."""
    blocks = [block for page in pages for block in (_Marker(page.label), *page.blocks)]
    items = find_items(blocks)
    blocks = [
        _Heading(items[i], _title(items[i], block)) if i in items else block
        for i, block in enumerate(blocks)
    ]
    return _render(_rejoin(blocks))


def find_items(blocks: list) -> dict[int, str]:
    """Which blocks are Item headings: block index → Item ("1A").

    Only a heading that advances the sequence is accepted, which drops cross-
    references ("Item 1A. Risk Factors" quoted in MD&A). Headings that restart
    at Item 1 discard every one accepted before them: those were the table of
    contents.
    """
    accepted: list[tuple[int, str]] = []
    for index, block in enumerate(blocks):
        item = _item_candidate(block)
        if item is None:
            continue
        if accepted and ITEMS.index(item) <= ITEMS.index(accepted[-1][1]):
            if item == "1" and accepted[-1][1] != "1":
                accepted = [(index, item)]
            continue
        accepted.append((index, item))
    return dict(accepted)


def check_items(markdown: str) -> None:
    """Every Item a 10-K must have has a heading in the Markdown."""
    found = [match.group(2) for match in ITEM_HEADING.finditer(markdown)]
    missing = [
        item for item in ITEMS if item not in found and item not in OPTIONAL_ITEMS
    ]
    if missing:
        raise FilingError(
            f"no heading found for Item {', '.join(missing)}; found {', '.join(found) or 'none'}"
        )


def check_page_labels(labels: list[str | None]) -> None:
    """Labels must cover most pages and only ever increase.

    A body text line mistaken for a footer shows up as a label out of order.
    Within one prefix ("F-") numbers increase; a prefix, once left, stays left.
    """
    numbered = [label for label in labels if label]
    if len(numbered) < MIN_LABELED_PAGES * len(labels):
        raise FilingError(
            f"only {len(numbered)} of {len(labels)} pages print a recognized label"
        )
    seen_prefixes: set[str] = set()
    for previous, label in pairwise(numbered):
        (prefix, number), (next_prefix, next_number) = _split(previous), _split(label)
        seen_prefixes.add(prefix)
        if next_prefix == prefix and next_number <= number:
            raise FilingError(f"page label {label} follows {previous}")
        if next_prefix != prefix and next_prefix in seen_prefixes:
            raise FilingError(f"page label {label} follows {previous}")


class _Reader:
    """Flattens the body into text blocks, raw tables and page breaks."""

    def __init__(self) -> None:
        self.blocks: list[str | _Table | _PageBreak] = []
        self._inline: list[str] = []

    def read(self, element: ET.Element) -> None:
        style = element.get("style", "")
        if _HIDDEN.search(style):
            return
        tag = _local(element.tag)
        # Workiva styles every table `display:inline-table`; a table is still
        # its own block, after the text before it.
        is_block = tag == "table" or (tag in _BLOCK_TAGS and not _INLINE.search(style))
        if is_block:
            self._flush()
        if _BREAK_BEFORE.search(style):
            self._break()
        if tag == "table":
            self.blocks.append(_Table(_read_rows(element)))
        else:
            if tag == "br":
                self._inline.append(" ")
            if element.text:
                self._inline.append(element.text)
            for child in element:
                self.read(child)
                if child.tail:
                    self._inline.append(child.tail)
        if is_block:
            self._flush()
        if _BREAK_AFTER.search(style):
            self._break()

    def _flush(self) -> None:
        text = " ".join("".join(self._inline).split())
        self._inline = []
        if text:
            self.blocks.append(text)

    def _break(self) -> None:
        self._flush()
        self.blocks.append(_PageBreak())


def _body(root: ET.Element) -> ET.Element:
    body = next((child for child in root if _local(child.tag) == "body"), None)
    if body is None:
        raise FilingError("the document has no <body>")
    return body


def _local(tag: str) -> str:
    """`{http://www.w3.org/1999/xhtml}div` → `div`."""
    return tag.rpartition("}")[2]


def _read_rows(table: ET.Element) -> list[list[Cell]]:
    rows = []
    for row in _table_rows(table):
        if _HIDDEN.search(row.get("style", "")):
            continue
        cells, column = [], 0
        for cell in row:
            if _local(cell.tag) not in ("td", "th") or _HIDDEN.search(
                cell.get("style", "")
            ):
                continue
            span = int(cell.get("colspan", "1"))
            cells.append(Cell(column, column + span, _cell_text(cell)))
            column += span
        rows.append(cells)
    return rows


def _table_rows(table: ET.Element) -> list[ET.Element]:
    rows = []
    for child in table:
        tag = _local(child.tag)
        if tag == "tr":
            rows.append(child)
        elif tag in ("thead", "tbody", "tfoot"):
            rows.extend(row for row in child if _local(row.tag) == "tr")
    return rows


def _cell_text(cell: ET.Element) -> str:
    parts: list[str] = []

    def visit(element: ET.Element) -> None:
        if _HIDDEN.search(element.get("style", "")):
            return
        # Blocks inside a cell ("Year Ended" / "December 31,") are separate words.
        spaced = _local(element.tag) in _BLOCK_TAGS or _local(element.tag) == "br"
        if spaced:
            parts.append(" ")
        if element.text:
            parts.append(element.text)
        for child in element:
            visit(child)
            if child.tail:
                parts.append(child.tail)
        if spaced:
            parts.append(" ")

    visit(cell)
    return " ".join("".join(parts).split())


def _convert(raw: list) -> list[str | DataTable | _PageBreak]:
    """Render data tables, turn layout tables into text, and keep each data
    table's units line and footnotes in its block."""
    blocks: list[str | DataTable | _PageBreak] = []
    for block in raw:
        if isinstance(block, str) and _RULE_LINE.fullmatch(block):
            continue
        if isinstance(block, _Table):
            markdown = tables.to_markdown(block.rows)
            if markdown is None:
                blocks.extend(tables.to_lines(block.rows))
                continue
            if (
                blocks
                and isinstance(blocks[-1], str)
                and tables.is_units_line(blocks[-1])
            ):
                markdown = f"{blocks.pop()}\n{markdown}"
            blocks.append(DataTable(markdown))
        elif (
            isinstance(block, str)
            and blocks
            and isinstance(blocks[-1], DataTable)
            and _FOOTNOTE.match(block)
        ):
            blocks[-1] = DataTable(f"{blocks[-1].markdown}\n{block}")
        else:
            blocks.append(block)
    return blocks


def _split_pages(blocks: list) -> list[list[str | DataTable]]:
    pages: list[list[str | DataTable]] = [[]]
    for block in blocks:
        if isinstance(block, _PageBreak):
            pages.append([])
        else:
            pages[-1].append(block)
    return pages


def _page(blocks: list[str | DataTable]) -> Page:
    label = _footer_label(blocks[-1]) if blocks else None
    if label is not None:
        blocks = blocks[:-1]
    start = 0
    while (
        start < len(blocks)
        and isinstance(blocks[start], str)
        and _RUNNING_HEADER.fullmatch(blocks[start])
    ):
        start += 1
    start = _after_continued_header(blocks, start)
    kept = [
        _bulleted(block) if isinstance(block, str) else block
        for block in blocks[start:]
        if not (isinstance(block, str) and _PART_LINE.fullmatch(block))
    ]
    return Page(label, kept)


def _after_continued_header(blocks: list[str | DataTable], start: int) -> int:
    for index in range(start, min(start + _CONTINUED_HEADER_MAX_LINES, len(blocks))):
        block = blocks[index]
        if not isinstance(block, str) or len(block) > _FOOTER_MAX_LENGTH:
            break
        if _CONTINUED.fullmatch(block):
            return index + 1
    return start


def _footer_label(block: str | DataTable) -> str | None:
    if not isinstance(block, str) or len(block) > _FOOTER_MAX_LENGTH:
        return None
    token = block.split()[-1].rstrip(".")
    return token if _PAGE_LABEL.fullmatch(token) else None


def _bulleted(text: str) -> str:
    return _BULLET.sub("- ", text, count=1) if _BULLET.match(text) else text


def _split(label: str) -> tuple[str, int]:
    prefix, _, number = label.rpartition("-")
    return prefix, int(number)


def _item_candidate(block) -> str | None:
    if not isinstance(block, str) or len(block) > _HEADING_MAX_LENGTH:
        return None
    match = _ITEM_CANDIDATE.fullmatch(block)
    if match is None:
        return None
    item, period, title = match.group(1).upper(), match.group(2), match.group(3)
    # A heading carries a period or a title. "Item 1A of Part I …" is a
    # sentence, and a bare "Item 7" a running header that escaped stripping.
    if title:
        is_heading = _TITLE_START.match(title) is not None
    else:
        is_heading = period is not None
    return item if is_heading and item in ITEM_TITLES else None


def _title(item: str, heading: str) -> str:
    if item == "6" and _SELECTED_FINANCIAL_DATA.search(heading):
        return "Selected Financial Data"
    return ITEM_TITLES[item]


def _rejoin(blocks: list) -> list:
    """Rejoin paragraphs a page break cut in two, the marker kept inside.

    A page that opens with a bullet starts a new item, even when the one
    before it ends "…; and".
    """
    joined: list = []
    for block in blocks:
        if (
            isinstance(block, str)
            and len(joined) >= 2
            and isinstance(joined[-1], _Marker)
            and isinstance(joined[-2], str)
            and not _COMPLETE.search(joined[-2])
            and not block.startswith("- ")
            and (block[:1].islower() or _CUT_OFF.search(joined[-2]))
        ):
            marker = joined.pop()
            joined[-1] = f"{joined[-1]} {page_marker(marker.label)} {block}"
            continue
        joined.append(block)
    return joined


def _render(blocks: list) -> str:
    parts = []
    for block in blocks:
        if isinstance(block, _Marker):
            parts.append(page_marker(block.label))
        elif isinstance(block, _Heading):
            parts.append(item_heading(block.item, block.title))
        elif isinstance(block, DataTable):
            parts.append(block.markdown)
        else:
            parts.append(block)
    return "\n\n".join(parts) + "\n"
