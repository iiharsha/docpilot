"""Markdown → retrieval chunks. A pure function of the stored Markdown.

Chunks never cross an Item heading, so every chunk's section is exact. Within
an Item, paragraphs and tables are packed to about `TARGET_TOKENS`, never more
than `MAX_TOKENS`, and each chunk after the first repeats the last sentences of
the one before it. A table stays whole if it fits under the maximum. A larger
one is split by rows, and each later piece repeats the table's header and the
group label its rows sit under — without "International" above it, Amazon's
"Operating income (7,746)" says nothing.

A chunk's `content` is a short prefix (that repeated header, for table pieces;
empty otherwise), then one contiguous stretch of the Markdown with its page
markers removed. `verify` holds every chunk to exactly that.
"""

import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass

from ingest import FilingError
from ingest.markdown import ITEM_HEADING, PAGE_MARKER, strip_markers

TARGET_TOKENS = 500
MAX_TOKENS = 800
# Overlap is whole sentences, up to this many tokens.
OVERLAP_TOKENS = 80
# A chunk still this small may grow past the target, up to the maximum,
# rather than let a table be separated from the line that introduces it.
MIN_TOKENS = TARGET_TOKENS // 2

TokenCounter = Callable[[str], int]

# A block is a run of non-blank lines; blocks are separated by one blank line.
_BLOCK = re.compile(r"[^\n]+(?:\n[^\n]+)*")
_LINE = re.compile(r"[^\n]+")
_SEPARATOR_ROW = re.compile(r"^\| --- ", re.MULTILINE)
_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*(?=\s+[\"'“‘(\[]?[A-Z0-9$])")
# Words whose period does not end a sentence: "U.S. Securities", "Apple Inc.".
_ABBREVIATIONS = {
    "co", "corp", "dr", "e.g", "etc", "i.e", "inc", "jr", "llc", "ltd", "mr",
    "mrs", "ms", "no", "nos", "sr", "st", "u.k", "u.s", "vs",
}  # fmt: skip
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    section: str
    page: str | None
    content: str
    prefix_len: int
    # `content[prefix_len:] == strip_markers(markdown[start:end])`.
    start: int
    end: int
    token_count: int
    chunk_type: str
    # Piece n of m, when a table was too large to stay whole.
    table_part: tuple[int, int] | None = None


@dataclass(frozen=True)
class _Unit:
    """A span no chunk boundary falls inside: a paragraph, a whole table, or
    a piece of either."""

    start: int
    end: int
    tokens: int
    is_table: bool
    prefix: str = ""
    table_part: tuple[int, int] | None = None


class _Text:
    """The Markdown being chunked, and the counter its chunks are sized with."""

    def __init__(self, markdown: str, count_tokens: TokenCounter) -> None:
        self.markdown = markdown
        self.count_tokens = count_tokens

    def tokens(self, start: int, end: int, prefix: str = "") -> int:
        return self.count_tokens(prefix + strip_markers(self.markdown[start:end]))


def chunk_markdown(markdown: str, count_tokens: TokenCounter) -> list[Chunk]:
    """Every Item's chunks, in document order.

    Text before the first Item — the cover page and table of contents — is
    stored with the filing but not chunked: it belongs to no Item, and it is
    not what analysts ask about.
    """
    text = _Text(markdown, count_tokens)
    markers = [(m.start(), m.group(1)) for m in PAGE_MARKER.finditer(markdown)]
    headings = list(ITEM_HEADING.finditer(markdown))
    chunks = []
    for heading, following in zip(headings, [*headings[1:], None], strict=True):
        end = following.start() if following else len(markdown)
        for group, overlap in _pack(text, _units(text, heading.end(), end)):
            chunks.append(_chunk(text, heading.group(1), group, overlap, markers))
    return chunks


def verify(markdown: str, chunks: list[Chunk]) -> None:
    """Hold every chunk to the offset rule and to the section it claims.

    Raises `FilingError`; run before anything is stored.
    """
    headings = [(m.start(), m.group(1)) for m in ITEM_HEADING.finditer(markdown)]
    positions = [position for position, _ in headings]
    for chunk in chunks:
        where = f"chunk at {chunk.start}–{chunk.end}"
        if chunk.content[chunk.prefix_len :] != strip_markers(
            markdown[chunk.start : chunk.end]
        ):
            raise FilingError(f"{where} does not match its offsets")
        index = bisect_right(positions, chunk.start) - 1
        if index < 0 or headings[index][1] != chunk.section:
            raise FilingError(f"{where} is not inside {chunk.section!r}")
        if index + 1 < len(positions) and positions[index + 1] < chunk.end:
            raise FilingError(f"{where} crosses into {headings[index + 1][1]!r}")
        if not chunk.content.strip():
            raise FilingError(f"{where} is empty")


def _units(text: _Text, start: int, end: int) -> list[_Unit]:
    units: list[_Unit] = []
    for block in _BLOCK.finditer(text.markdown, start, end):
        if PAGE_MARKER.fullmatch(block.group()):
            continue
        is_table = _SEPARATOR_ROW.search(block.group()) is not None
        tokens = text.tokens(block.start(), block.end())
        if tokens <= MAX_TOKENS:
            units.append(_Unit(block.start(), block.end(), tokens, is_table))
        elif is_table:
            units.extend(_table_pieces(text, block.start(), block.end()))
        else:
            units.extend(_text_pieces(text, block.start(), block.end()))
    return units


def _pack(
    text: _Text, units: list[_Unit]
) -> list[tuple[list[_Unit], tuple[int, int] | None]]:
    """Group units into chunks, each with the overlap span it opens with."""
    groups: list[tuple[list[_Unit], tuple[int, int] | None]] = []
    current: list[_Unit] = []
    overlap: tuple[int, int] | None = None
    tokens = 0
    for unit in units:
        if unit.table_part is not None and unit.table_part[0] > 1:
            # Each later piece of a table opens a chunk, and its prefix, not an
            # overlap, carries the context. The first piece packs like any
            # unit, so it keeps the title above it; text after the last packs
            # in behind it.
            if current:
                groups.append((current, overlap))
            current, overlap, tokens = [unit], None, unit.tokens
            continue
        fits = tokens + unit.tokens <= TARGET_TOKENS
        grows = tokens < MIN_TOKENS and tokens + unit.tokens <= MAX_TOKENS
        if current and not (fits or grows):
            groups.append((current, overlap))
            overlap = _overlap(text, current)
            tokens = text.tokens(*overlap) if overlap else 0
            current = []
        if not current and overlap and tokens + unit.tokens > MAX_TOKENS:
            overlap, tokens = None, 0
        current.append(unit)
        tokens += unit.tokens
    if current:
        groups.append((current, overlap))
    return groups


def _overlap(text: _Text, group: list[_Unit]) -> tuple[int, int] | None:
    """The span of the chunk's last sentences that fit in `OVERLAP_TOKENS`.

    It can reach back over several short paragraphs, which carries a title
    ("CONSOLIDATED BALANCE SHEETS") forward with what it introduces. It never
    reaches into a table.
    """
    end = group[-1].end
    start = None
    for unit in reversed(group):
        if unit.is_table:
            break
        for sentence_start, _ in reversed(
            _sentences(text.markdown, unit.start, unit.end)
        ):
            if text.tokens(sentence_start, end) > OVERLAP_TOKENS:
                return (start, end) if start is not None else None
            start = sentence_start
    return (start, end) if start is not None else None


def _chunk(
    text: _Text,
    section: str,
    group: list[_Unit],
    overlap: tuple[int, int] | None,
    markers: list[tuple[int, str | None]],
) -> Chunk:
    start = overlap[0] if overlap else group[0].start
    end = group[-1].end
    # Only a later table piece has a prefix, and it always opens its chunk.
    prefix = group[0].prefix
    content = prefix + strip_markers(text.markdown[start:end])
    return Chunk(
        section=section,
        page=_page(markers, start, end),
        content=content,
        prefix_len=len(prefix),
        start=start,
        end=end,
        token_count=text.count_tokens(content),
        chunk_type="table" if any(unit.is_table for unit in group) else "text",
        table_part=next((unit.table_part for unit in group if unit.table_part), None),
    )


def _page(markers: list[tuple[int, str | None]], start: int, end: int) -> str | None:
    """The printed page a span is on — "23" — or the pages it runs across — "22–23".

    Every document opens with a marker, so one always precedes `start`.
    """
    first = bisect_right([position for position, _ in markers], start) - 1
    labels = [label for position, label in markers[first:] if position < end and label]
    if not labels:
        return None
    return labels[0] if labels[0] == labels[-1] else f"{labels[0]}–{labels[-1]}"


def _sentences(markdown: str, start: int, end: int) -> list[tuple[int, int]]:
    sentences = []
    sentence_start = start
    for match in _SENTENCE_END.finditer(markdown, start, end):
        word = markdown[sentence_start : match.start() + 1].rsplit(maxsplit=1)[-1]
        stem = word.rstrip(".!?").lstrip("(\"'“‘").lower()
        if stem in _ABBREVIATIONS or (len(stem) == 1 and stem.isalpha()):
            continue
        sentences.append((sentence_start, match.end()))
        sentence_start = _WORD.search(markdown, match.end(), end).start()
    sentences.append((sentence_start, end))
    return sentences


def _text_pieces(text: _Text, start: int, end: int) -> list[_Unit]:
    """A paragraph over the maximum, as runs of whole sentences.

    A single sentence over the maximum — a run-on list — is cut between words.
    """
    spans = []
    for sentence in _sentences(text.markdown, start, end):
        if text.tokens(*sentence) > MAX_TOKENS:
            spans.extend(
                (m.start(), m.end()) for m in _WORD.finditer(text.markdown, *sentence)
            )
        else:
            spans.append(sentence)

    units = []
    run_start, run_end = spans[0]
    for span_start, span_end in spans[1:]:
        if text.tokens(run_start, span_end) > TARGET_TOKENS:
            units.append(
                _Unit(
                    run_start, run_end, text.tokens(run_start, run_end), is_table=False
                )
            )
            run_start = span_start
        run_end = span_end
    units.append(
        _Unit(run_start, run_end, text.tokens(run_start, run_end), is_table=False)
    )
    return units


def _table_pieces(text: _Text, start: int, end: int) -> list[_Unit]:
    """A table over the maximum, as runs of rows under its repeated header.

    The first piece opens with the table itself — units line, header — and
    the last closes with its footnotes.
    """
    markdown = text.markdown
    lines = [(m.start(), m.end()) for m in _LINE.finditer(markdown, start, end)]
    separator = next(
        i for i, (s, _) in enumerate(lines) if markdown.startswith("| --- ", s)
    )
    rows = [
        line for line in lines[separator + 1 :] if markdown.startswith("| ", line[0])
    ]
    head = markdown[start : lines[separator][1]] + "\n"
    budget = TARGET_TOKENS - text.count_tokens(head)

    runs: list[list[tuple[int, int]]] = [[]]
    run_tokens = 0
    for row in rows:
        row_tokens = text.count_tokens(markdown[row[0] : row[1]] + "\n")
        if runs[-1] and run_tokens + row_tokens > budget:
            runs.append([])
            run_tokens = 0
        runs[-1].append(row)
        run_tokens += row_tokens

    pieces = []
    group_label = ""
    for n, run in enumerate(runs, start=1):
        piece_start = start if n == 1 else run[0][0]
        piece_end = end if n == len(runs) else run[-1][1]
        prefix = ""
        if n > 1:
            opens_group = _is_group_label(markdown[run[0][0] : run[0][1]])
            prefix = head + (
                group_label + "\n" if group_label and not opens_group else ""
            )
        pieces.append(
            _Unit(
                piece_start,
                piece_end,
                text.tokens(piece_start, piece_end, prefix),
                is_table=True,
                prefix=prefix,
                table_part=(n, len(runs)),
            )
        )
        for row in run:
            if _is_group_label(markdown[row[0] : row[1]]):
                group_label = markdown[row[0] : row[1]]
    return pieces


def _is_group_label(row: str) -> bool:
    """A row naming the group below it: "| North America |  |  |  |"."""
    cells = re.split(r"(?<!\\) \| ", row[2:-2])
    return bool(cells[0].strip()) and not any(cell.strip() for cell in cells[1:])
