"""Real filing pages for the ingestion tests (see `fixtures/README.md`).

Chunks are sized by counting words rather than with tiktoken, which downloads
its encoding on first use and would take the fast suite onto the network.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest

from ingest import xhtml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def filing_root() -> Callable[[str], ET.Element]:
    def load(name: str) -> ET.Element:
        return ET.parse(FIXTURES / name).getroot()

    return load


@pytest.fixture
def filing_markdown(filing_root) -> Callable[[str], str]:
    """A fixture's pages as Markdown — without `to_markdown`'s checks, which
    a few pages of a filing cannot pass."""

    def render(name: str) -> str:
        return xhtml.render(xhtml.read_pages(filing_root(name)))

    return render


@pytest.fixture
def count_tokens() -> Callable[[str], int]:
    return lambda text: len(text.split())
