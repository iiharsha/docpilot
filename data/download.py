# /// script
# requires-python = ">=3.12"
# ///
"""Download a 10-K sample from SEC EDGAR into year folders under data/downloads/.

Edit the parameters below — especially USER_AGENT — then run:

    uv run data/download.py
"""

import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib import request

# --- Parameters ---

# SEC fair access requires a descriptive User-Agent naming a real contact.
# Anonymous and generic agents get 403s. Format: "Organization Name email@domain".
USER_AGENT = "Document Copilot your.email@example.com"

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]

COMPANY_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "GOOGL": "0001652044",
}

FORM = "10-K"
FILINGS_PER_COMPANY = 5

# SEC allows 10 requests/second; one request per interval stays well under.
REQUEST_INTERVAL = 0.2

OUTPUT_DIR = Path(__file__).resolve().parent / "downloads"
CLEAR_OUTPUT_DIR = True

SUBMISSIONS_BASE = "https://data.sec.gov/submissions/"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

# --- Script ---


def fetch(url: str, accept: str) -> bytes:
    """Rate-limited GET. EDGAR blocks clients that ignore its fair-access limits."""
    time.sleep(REQUEST_INTERVAL)
    req = request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=60) as response:
        return response.read()


def fetch_json(url: str) -> dict:
    return json.loads(fetch(url, "application/json"))


def target_years() -> set[str]:
    """The FILINGS_PER_COMPANY fiscal years ending before the current one.

    The current year is excluded because its 10-K is usually not filed yet.
    """
    current_year = datetime.now(UTC).year
    first_year = current_year - FILINGS_PER_COMPANY
    return {str(year) for year in range(first_year, current_year)}


def select_filings(index: dict, years: set[str]) -> list[dict]:
    """Zip EDGAR's parallel arrays into records for FORM filings covering `years`.

    Exact form match drops amendments (10-K/A), which restate a filing we have.
    """
    filings = []
    for form, accession, document, filing_date, report_date in zip(
        index["form"],
        index["accessionNumber"],
        index["primaryDocument"],
        index["filingDate"],
        index["reportDate"],
        strict=True,
    ):
        # Fiscal year comes from the period covered, not the filing date: a
        # FY2023 10-K filed in January 2024 belongs under 2023.
        year = (report_date or filing_date)[:4]
        if form == FORM and year in years:
            filings.append(
                {
                    "year": year,
                    "form": form,
                    "accession_number": accession,
                    "primary_document": document,
                    "filing_date": filing_date,
                    "report_date": report_date,
                }
            )
    return filings


def find_filings(cik: str, years: set[str]) -> list[dict]:
    """Newest-first filings, reaching into older shards when `recent` runs short.

    `recent` holds the last 1000 filings of every type. Frequent filers can push
    a five-year 10-K history off the end of it.
    """
    submissions = fetch_json(f"{SUBMISSIONS_BASE}CIK{cik}.json")["filings"]
    filings = select_filings(submissions["recent"], years)

    for shard in submissions.get("files", []):
        if len(filings) >= FILINGS_PER_COMPANY:
            break
        shard_index = fetch_json(SUBMISSIONS_BASE + shard["name"])
        filings.extend(select_filings(shard_index, years))

    return filings[:FILINGS_PER_COMPANY]


def download(ticker: str, cik: str, filing: dict) -> dict:
    """Fetch one filing into its fiscal-year folder and return its manifest record."""
    accession = filing["accession_number"]
    url = ARCHIVE_URL.format(
        cik=int(cik),
        accession=accession.replace("-", ""),
        document=filing["primary_document"],
    )
    suffix = Path(filing["primary_document"]).suffix or ".html"
    name = (
        f"{ticker.lower()}_{filing['form'].lower()}"
        f"_{filing['filing_date']}_{accession}{suffix}"
    )
    path = OUTPUT_DIR / filing["year"] / name

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch(url, "text/html,application/xhtml+xml,application/xml"))

    return {
        "ticker": ticker,
        "cik": cik,
        "form": filing["form"],
        "filing_date": filing["filing_date"],
        "report_date": filing["report_date"],
        "accession_number": accession,
        "primary_document": filing["primary_document"],
        "source_url": url,
        "local_path": str(path.relative_to(OUTPUT_DIR)),
    }


def main() -> None:
    if "example.com" in USER_AGENT:
        raise SystemExit(
            "Set USER_AGENT at the top of this script to your own name and email.\n"
            "SEC EDGAR rejects anonymous requests with 403."
        )

    if CLEAR_OUTPUT_DIR and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    years = target_years()
    records = []
    for ticker in TICKERS:
        print(f"Downloading {ticker} filings...")
        cik = COMPANY_CIKS[ticker]
        filings = find_filings(cik, years)
        if len(filings) < FILINGS_PER_COMPANY:
            print(f"  only {len(filings)} of {FILINGS_PER_COMPANY} found")
        records.extend(download(ticker, cik, filing) for filing in filings)

    manifest = {
        "source": "SEC EDGAR",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "form": FORM,
        "downloaded_count": len(records),
        "filings": records,
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\nDownloaded {len(records)} filing(s) to {OUTPUT_DIR}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
