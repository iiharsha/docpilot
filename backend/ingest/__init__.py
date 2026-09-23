"""Corpus ingestion: EDGAR 10-K XHTML → Markdown → chunks → embeddings → Postgres.

Run with `uv run python -m ingest`; see `__main__` for the options.
"""


class FilingError(Exception):
    """A filing lacks structure the pipeline relies on, so it is not ingested.

    Raised instead of guessing: a filing that parses into the wrong sections or
    pages would still produce confident, well-cited answers — just wrong ones.
    """
