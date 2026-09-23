"""A filing's identity: the download manifest's record plus its cover-page facts.

The manifest knows ticker, CIK, form, accession number, dates and URL. The
company's name and fiscal year are read from the filing's own `dei:` tags,
which usually sit in the hidden `ix:header` — so they are looked for in a
separate pass over the whole tree, not in the text the converter keeps.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

from ingest import FilingError

_IX_TAGS = {
    "{http://www.xbrl.org/2013/inlineXBRL}nonNumeric",
    "{http://www.xbrl.org/2013/inlineXBRL}nonFraction",
}


@dataclass(frozen=True)
class Filing:
    ticker: str
    cik: str
    company_name: str
    form_type: str
    accession_number: str
    filing_date: date
    # The period the filing covers. NVIDIA's fiscal 2025 ended in January
    # 2025, Microsoft's in June; the filing date says neither.
    period_end_date: date
    fiscal_year: int
    source_url: str


def read_filing(record: dict, root: ET.Element) -> Filing:
    """Combine a `data/downloads/manifest.json` record with the filing's tags.

    The fiscal year the filer tags must agree with the manifest's period end,
    since retrieval filters on it and the brief's questions are by year.
    """
    tags = _dei_tags(root)
    period_end = date.fromisoformat(record["report_date"])
    fiscal_year = int(_required(tags, "DocumentFiscalYearFocus"))
    if fiscal_year != period_end.year:
        raise FilingError(
            f"fiscal year {fiscal_year} is tagged, but the period ends {period_end}"
        )
    return Filing(
        ticker=record["ticker"],
        cik=record["cik"],
        company_name=_required(tags, "EntityRegistrantName"),
        form_type=record["form"],
        accession_number=record["accession_number"],
        filing_date=date.fromisoformat(record["filing_date"]),
        period_end_date=period_end,
        fiscal_year=fiscal_year,
        source_url=record["source_url"],
    )


def _dei_tags(root: ET.Element) -> dict[str, str]:
    """The first value of each `dei:` fact, hidden or not, by local name."""
    tags: dict[str, str] = {}
    for element in root.iter():
        if element.tag not in _IX_TAGS:
            continue
        prefix, _, name = element.get("name", "").partition(":")
        if prefix == "dei" and name not in tags:
            tags[name] = " ".join("".join(element.itertext()).split())
    return tags


def _required(tags: dict[str, str], name: str) -> str:
    value = tags.get(name)
    if not value:
        raise FilingError(f"the filing does not tag dei:{name}")
    return value
