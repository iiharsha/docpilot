"""Ingest the downloaded 10-K sample: `uv run python -m ingest [--ticker AAPL] [--dry-run]`.

Reads `data/downloads/manifest.json`, which `data/download.py` writes. Each
filing is parsed, converted to Markdown, chunked and checked, then embedded and
stored in a transaction of its own; a filing that fails a check is reported and
skipped, and leaves whatever was stored for it before untouched.

`--dry-run` stops before the embeddings API and the database, and prints what
each filing produced. It is the loop to tune chunking in.
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import tiktoken
from openai import OpenAI

from app.config import settings
from ingest import FilingError, chunker, embed, metadata, store, xhtml
from ingest.chunker import Chunk, TokenCounter
from ingest.markdown import ITEM_HEADING, PAGE_MARKER
from ingest.metadata import Filing

DOWNLOADS = Path(__file__).resolve().parents[2] / "data" / "downloads"
# The tokenizer text-embedding-3-small counts with. tiktoken downloads it on
# first use and caches it.
ENCODING = "cl100k_base"
# The embedding endpoint rate-limits bursts; the SDK backs off and retries.
OPENAI_MAX_RETRIES = 5

_TABLE_SEPARATOR = re.compile(r"^\| --- ", re.MULTILINE)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    manifest = json.loads((DOWNLOADS / "manifest.json").read_text(encoding="utf-8"))
    records = [
        record
        for record in manifest["filings"]
        if args.ticker in (None, record["ticker"])
    ]
    if not records:
        raise SystemExit(f"no {args.ticker} filings in {DOWNLOADS / 'manifest.json'}")

    encoding = tiktoken.get_encoding(ENCODING)

    def count_tokens(text: str) -> int:
        # Filing text is data: a "<|endoftext|>" in it is just characters.
        return len(encoding.encode(text, disallowed_special=()))

    if not args.dry_run:
        engine = store.create_ingest_engine()
        client = OpenAI(api_key=settings.openai_api_key, max_retries=OPENAI_MAX_RETRIES)

    failed = []
    total_chunks = total_tokens = 0
    for record in records:
        try:
            filing, markdown, chunks = _prepare(record, count_tokens)
        except FilingError as error:
            print(f"{record['local_path']}: FAILED — {error}")
            failed.append(record["local_path"])
            continue
        print(_summary(filing, markdown, chunks), flush=True)
        total_chunks += len(chunks)
        total_tokens += sum(chunk.token_count for chunk in chunks)
        if args.dry_run:
            continue
        texts = [embed.embedding_text(filing, chunk) for chunk in chunks]
        vectors = embed.embed(
            client, settings.openai_embedding_model, texts, count_tokens
        )
        with engine.begin() as connection:
            store.store_filing(
                connection,
                store.document_row(filing, markdown),
                store.chunk_rows(filing, chunks, vectors),
            )

    print(
        f"{len(records) - len(failed)} filings, {total_chunks:,} chunks, {total_tokens:,} tokens"
    )
    if not args.dry_run and args.ticker is None:
        store.vacuum(engine)
    if failed:
        print(f"{len(failed)} failed: {', '.join(failed)}")
    return 1 if failed else 0


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m ingest", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--ticker", type=str.upper, help="only this company's filings, e.g. AAPL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse, chunk and report, without calling the embeddings API or writing anything",
    )
    return parser.parse_args(argv)


def _prepare(
    record: dict, count_tokens: TokenCounter
) -> tuple[Filing, str, list[Chunk]]:
    root = ET.parse(DOWNLOADS / record["local_path"]).getroot()
    filing = metadata.read_filing(record, root)
    markdown = xhtml.to_markdown(root)
    chunks = chunker.chunk_markdown(markdown, count_tokens)
    chunker.verify(markdown, chunks)
    return filing, markdown, chunks


def _summary(filing: Filing, markdown: str, chunks: list[Chunk]) -> str:
    items = [match.group(2) for match in ITEM_HEADING.finditer(markdown)]
    missing = [item for item in xhtml.ITEMS if item not in items]
    labels = [match.group(1) for match in PAGE_MARKER.finditer(markdown)]
    labeled = [label for label in labels if label]
    tables = len(_TABLE_SEPARATOR.findall(markdown))
    split = sum(1 for chunk in chunks if chunk.table_part and chunk.table_part[0] == 1)
    return (
        f"{filing.ticker:<5} FY{filing.fiscal_year}  {filing.accession_number}  "
        f"items {len(items)}/{len(xhtml.ITEMS)}{f' (no {", ".join(missing)})' if missing else ''}  "
        f"pages {len(labeled)}/{len(labels)} labeled, {labeled[0]}–{labeled[-1]}  "
        f"chunks {len(chunks)}  tokens {sum(chunk.token_count for chunk in chunks):,}  "
        f"tables {tables} ({split} split)"
    )


if __name__ == "__main__":
    raise SystemExit(main())
