"""The one guard every direct database user goes through: Alembic, ingestion, retrieval."""

import pytest

from app.config import settings
from app.database.engine import session_database_url

POOLER = "aws-0-us-east-1.pooler.supabase.com"


def test_the_transaction_pooler_is_refused(monkeypatch):
    monkeypatch.setattr(
        settings,
        "database_url",
        f"postgresql://postgres.ref:secret@{POOLER}:6543/postgres",
    )

    with pytest.raises(RuntimeError, match="transaction pooler"):
        session_database_url()


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql://postgres.ref:secret@{POOLER}:5432/postgres",
        "postgresql://postgres:secret@db.ref.supabase.co:5432/postgres",
    ],
)
def test_a_session_connection_is_accepted_in_sqlalchemy_form(monkeypatch, url):
    monkeypatch.setattr(settings, "database_url", url)

    assert session_database_url() == url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
