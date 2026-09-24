"""Direct Postgres over `DATABASE_URL`, for what PostgREST cannot do.

Migrations, ingestion's one-transaction writes and retrieval's vector and
full-text searches all connect here rather than through the Supabase client,
and all of them need a session connection.
"""

from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings


def session_database_url() -> str:
    """`DATABASE_URL` in SQLAlchemy's form, refusing Supabase's transaction pooler.

    The transaction pooler (port 6543) hands each transaction whichever server
    connection is free. Migrations, `create extension` and index builds need a
    session of their own, and psycopg prepares a statement once it has run a
    few times on a connection — the next transaction may land on a server
    connection where that statement does not exist. The session pooler (port
    5432) and the direct connection are both fine.
    """
    url = urlsplit(settings.database_url)
    if url.hostname and "pooler.supabase.com" in url.hostname and url.port == 6543:
        raise RuntimeError(
            "DATABASE_URL points at the Supabase transaction pooler (port 6543). "
            "Use a session connection: the session pooler (port 5432) or the "
            "direct connection (db.<project-ref>.supabase.co:5432)."
        )
    return settings.sqlalchemy_database_url


def create_database_engine() -> AsyncEngine:
    """The app's connection pool, built once in `main.lifespan`.

    Nothing connects until first use. `pool_pre_ping` tests a pooled
    connection before handing it out, since a pooler or proxy can drop one
    that sat idle, and the request that drew it would fail.
    """
    return create_async_engine(session_database_url(), pool_pre_ping=True)
