"""Alembic environment.

The SQLAlchemy models are the source of truth for the schema; this file only
wires Alembic to them and to the database URL from `app.config.settings`.
"""

from logging.config import fileConfig
from urllib.parse import urlsplit

from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine, pool

from app.config import settings
from app.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Schema migrations, `create extension`, and index builds need a session
# connection. Supabase's transaction pooler (port 6543) silently breaks all
# three; its session pooler (5432) and the direct connection are both fine.
_url = urlsplit(settings.database_url)
if _url.hostname and "pooler.supabase.com" in _url.hostname and _url.port == 6543:
    raise RuntimeError(
        "DATABASE_URL points at the Supabase transaction pooler (port 6543). "
        "Alembic needs a session connection: use the session pooler (port 5432) "
        "or the direct connection (db.<project-ref>.supabase.co:5432)."
    )

# The URL never lives in alembic.ini, and is never written into it either:
# `settings` is the single source of env, and a `%` from a URL-encoded password
# would be read as configparser interpolation syntax.
DATABASE_URL = settings.sqlalchemy_database_url

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Keep autogenerate from proposing drops for objects we don't own.

    `public` in a Supabase project also holds things this app did not create.
    """
    unmodeled_table = (
        type_ == "table" and reflected and name not in target_metadata.tables
    )
    return not unmodeled_table


def render_item(type_, obj, autogen_context) -> str | bool:
    """Render `vector(n)` columns as pgvector's type, not `sa.VECTOR`."""
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("import pgvector.sqlalchemy")
        return f"pgvector.sqlalchemy.Vector(dim={obj.dim})"
    return False


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or manual apply."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        render_item=render_item,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            render_item=render_item,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
