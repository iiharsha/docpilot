"""The normalized Markdown that `xhtml` writes and `chunker` reads.

It is stored in `source_documents.markdown`, and every stored chunk's offsets
point into it, so this format is a contract with rows already in the database:

- `## Item 7. Management's Discussion and …` opens a 10-K Item. Nothing else
  uses `##`, so a heading line is always an Item boundary.
- `<!-- page 23 -->` marks where a printed page begins, labelled with the number
  in that page's own footer. `<!-- page -->` begins a page that prints none.
  A marker is usually a block of its own. When a page break cuts a paragraph in
  two, it sits inside the rejoined paragraph instead, so the sentence stays
  whole and the page boundary stays exact.
- Blocks are separated by exactly one blank line, and never contain one. A data
  table is one block: its units line, the pipe table, then its footnotes.
"""

import re

ITEM_HEADING = re.compile(r"^## (Item (\d{1,2}[A-C]?)\. .+)$", re.MULTILINE)
PAGE_MARKER = re.compile(r"<!-- page(?: (\S+))? -->")
# A marker together with what separates it from the text it sits between, so
# removing it leaves that text exactly as if the marker had never been there.
_MARKER_AND_SEPARATOR = re.compile(r"<!-- page(?: \S+)? -->(?:\n\n| |$)")


def item_heading(item: str, title: str) -> str:
    return f"## Item {item}. {title}"


def page_marker(label: str | None) -> str:
    return f"<!-- page {label} -->" if label else "<!-- page -->"


def strip_markers(text: str) -> str:
    """The passage as a reader sees it: `text` without its page markers."""
    return _MARKER_AND_SEPARATOR.sub("", text)
