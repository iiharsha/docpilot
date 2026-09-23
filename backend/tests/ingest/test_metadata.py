"""A filing's identity: the download manifest's record, plus its cover-page tags."""

from datetime import date

import pytest

from ingest import FilingError
from ingest.metadata import Filing, read_filing

# Apple's FY2024 record, as `data/download.py` writes it to manifest.json.
APPLE_2024 = {
    "ticker": "AAPL",
    "cik": "0000320193",
    "form": "10-K",
    "filing_date": "2024-11-01",
    "report_date": "2024-09-28",
    "accession_number": "0000320193-24-000123",
    "primary_document": "aapl-20240928.htm",
    "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
    "local_path": "2024/aapl_10-k_2024-11-01_0000320193-24-000123.htm",
}


def test_identity_joins_the_manifest_and_the_cover_page(filing_root):
    filing = read_filing(APPLE_2024, filing_root("aapl_2024_front.htm"))

    # The company name is tagged on the visible cover; the fiscal year only
    # in the hidden ix:header.
    assert filing == Filing(
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        form_type="10-K",
        accession_number="0000320193-24-000123",
        filing_date=date(2024, 11, 1),
        period_end_date=date(2024, 9, 28),
        fiscal_year=2024,
        source_url=APPLE_2024["source_url"],
    )


def test_a_fiscal_year_the_period_does_not_end_in_is_refused(filing_root):
    record = {**APPLE_2024, "report_date": "2023-09-30"}

    with pytest.raises(
        FilingError, match="fiscal year 2024 is tagged, but the period ends 2023-09-30"
    ):
        read_filing(record, filing_root("aapl_2024_front.htm"))


def test_a_filing_without_its_cover_tags_is_refused(filing_root):
    # Pages from the middle of the filing carry no dei: tags.
    with pytest.raises(FilingError, match="dei:DocumentFiscalYearFocus"):
        read_filing(APPLE_2024, filing_root("aapl_2024_net_sales.htm"))
