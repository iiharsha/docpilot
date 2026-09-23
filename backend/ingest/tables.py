"""EDGAR data tables → Markdown pipe tables.

Filers lay a table out on a fine grid and spread each figure over several
cells. Workiva, which generates the Apple, Amazon, Alphabet and NVIDIA filings,
writes `$` | `201,183` | `` under a header that spans all three. DFIN, which
generates Microsoft's, writes `(2,935` | `)`, with the header over one of those
cells and the `$` and `)` in empty grid columns beside it.

So each row's cells are glued back into whole values first — a lone currency
sign onto the next cell, a lone `)` or `%` onto the previous one — and each
value is then placed under the header column it overlaps most. A table without
a single figure in it is layout (Amazon's Item headings, bullet lists,
signature blocks), and comes back as text lines instead.
"""

import re
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class Cell:
    """A cell's text and the grid columns `[start, end)` it covers."""

    start: int
    end: int
    text: str


_CURRENCY = re.compile(r"[$€£¥]")
_CLOSING = re.compile(r"[)%]+")
# A whole figure: `$201,183`, `(2,935)`, `(2)%`, `13%`, `3.1`.
_FIGURE = re.compile(r"\(?[$€£¥]?\s*\(?-?\d[\d,]*(?:\.\d+)?\)?\s*%?\)?")
_YEAR = re.compile(r"(?:19|20)\d\d")
# "(In millions)", "($ in millions, except per share data)", and the lead-in
# that says it: "… net sales by category for 2024, 2023 and 2022 (dollars in
# millions):".
_UNITS = re.compile(r"\bin (?:millions|thousands|billions)\b.*[):]$", re.IGNORECASE)
_UNITS_MAX_LENGTH = 160


def to_lines(rows: list[list[Cell]]) -> list[str]:
    """A layout table's rows as text, one line per row."""
    lines = (" ".join(cell.text for cell in row if cell.text) for row in rows)
    return [line for line in lines if line]


def is_units_line(text: str) -> bool:
    return len(text) <= _UNITS_MAX_LENGTH and _UNITS.search(text) is not None


def to_markdown(rows: list[list[Cell]]) -> str | None:
    """A data table as one Markdown block, or None if it holds no figures.

    The header is the leading rows before the first figure, merged into one
    row: a header cell spanning several columns ("Year Ended December 31,")
    joins the header of each. A units line among them moves above the table.
    """
    rows = [glued for row in rows if (glued := _glue(row))]
    first_figures = next((i for i, row in enumerate(rows) if _has_figures(row)), None)
    if first_figures is None:
        return None

    head, body = rows[:first_figures], rows[first_figures:]
    units = [
        row[0].text for row in head if len(row) == 1 and is_units_line(row[0].text)
    ]
    head = [row for row in head if not (len(row) == 1 and is_units_line(row[0].text))]
    # A lone label just above the figures names their group ("North America"),
    # and has to stay with them rather than be merged into the header.
    while head and len(head[-1]) == 1:
        body.insert(0, head.pop())

    columns = _columns(head, body)
    header = [[] for _ in columns]
    for row in head:
        for cell in row:
            for i in _spanned(cell, columns):
                header[i].append(cell.text)
    grid = [[[] for _ in columns] for _ in body]
    for cells, row in zip(grid, body, strict=True):
        for cell in row:
            cells[_placed(cell, row, columns)].append(cell.text)

    # Spacer columns end up holding nothing but a spanning header's text.
    kept = [i for i in range(len(columns)) if any(cells[i] for cells in grid)]
    lines = [
        *units,
        _pipe_row(" ".join(header[i]) for i in kept),
        _pipe_row("---" for _ in kept),
        *(_pipe_row(" ".join(cells[i]) for i in kept) for cells in grid),
    ]
    return "\n".join(lines)


def _glue(row: list[Cell]) -> list[Cell]:
    """Rejoin each figure's pieces, dropping empty cells."""
    glued: list[Cell] = []
    currency: Cell | None = None
    for cell in row:
        if not cell.text:
            continue
        if currency is None and glued and _CLOSING.fullmatch(cell.text):
            last = glued.pop()
            glued.append(Cell(last.start, cell.end, last.text + cell.text))
            continue
        if currency is not None:
            cell = Cell(currency.start, cell.end, currency.text + cell.text)
            currency = None
        if _CURRENCY.fullmatch(cell.text):
            currency = cell
            continue
        glued.append(cell)
    if currency is not None:
        glued.append(currency)
    return glued


def _is_figure(text: str) -> bool:
    return _FIGURE.fullmatch(text) is not None and _YEAR.fullmatch(text) is None


def _has_figures(row: list[Cell]) -> bool:
    # A row's first cell is its label. Leaving it out keeps footnote tables —
    # "(1)" | "Includes …" — from reading as figures.
    return any(_is_figure(cell.text) for cell in row[1:])


def _columns(head: list[list[Cell]], body: list[list[Cell]]) -> list[tuple[int, int]]:
    """Column spans: the header row naming the most columns, plus any body
    cell that falls under none of them — usually the row labels, whose
    header cell is empty.

    A header can also sit over two figures in every row, an amount and its
    percentage (NVIDIA's tax rate reconciliation). That header is two columns,
    split where the second figure begins; its text then heads both.
    """
    template = max(reversed(head or body), key=len)
    columns = sorted((cell.start, cell.end) for cell in template)
    for row in body:
        for cell in row:
            if _is_group_label(cell, row):
                continue
            if not any(_overlap(cell, column) for column in columns):
                columns.append((cell.start, cell.end))
                columns.sort()
    for row in body:
        shared: dict[int, list[Cell]] = {}
        for cell in row:
            if not _is_group_label(cell, row):
                shared.setdefault(_placed(cell, row, columns), []).append(cell)
        for index in sorted(shared, reverse=True):
            start, end = columns[index]
            later = shared[index][1:]
            cuts = sorted(
                {start, end, *(c.start for c in later if start < c.start < end)}
            )
            columns[index : index + 1] = list(pairwise(cuts))
    return columns


def _is_group_label(cell: Cell, row: list[Cell]) -> bool:
    return len(row) == 1 and not _is_figure(cell.text)


def _overlap(cell: Cell, column: tuple[int, int]) -> int:
    return max(0, min(cell.end, column[1]) - max(cell.start, column[0]))


def _spanned(cell: Cell, columns: list[tuple[int, int]]) -> list[int]:
    spanned = [i for i, column in enumerate(columns) if _overlap(cell, column)]
    return spanned or [_nearest(cell, columns)]


def _placed(cell: Cell, row: list[Cell], columns: list[tuple[int, int]]) -> int:
    """The column a body cell belongs in; the leftmost on a tie."""
    if _is_group_label(cell, row):
        return 0
    return max(range(len(columns)), key=lambda i: (_overlap(cell, columns[i]), -i))


def _nearest(cell: Cell, columns: list[tuple[int, int]]) -> int:
    def gap(i: int) -> int:
        start, end = columns[i]
        return max(start - cell.end, cell.start - end)

    return min(range(len(columns)), key=gap)


def _pipe_row(cells) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"
