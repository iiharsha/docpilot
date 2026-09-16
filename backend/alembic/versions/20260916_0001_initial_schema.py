"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-16

Targets Supabase Postgres specifically: it references `auth.users`, `auth.uid()`,
and the `authenticated` role, none of which exist on a stock Postgres server.

Everything autogenerate cannot infer is written out here: the `vector` extension,
the `public.users` -> `auth.users` foreign key, the HNSW and GIN indexes, and RLS
enablement plus policies.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# RLS is on for every table. The backend reaches Postgres as the table owner (and
# PostgREST as `service_role`), so both bypass RLS; these policies bound what a
# user's own Supabase anon/authenticated key could ever read if it were used
# directly. Writes are backend-only, so no write policies exist.
USER_OWNED_POLICIES = (
    """
    create policy users_select_own on public.users
        for select to authenticated
        using (id = (select auth.uid()))
    """,
    """
    create policy chat_threads_select_own on public.chat_threads
        for select to authenticated
        using (user_id = (select auth.uid()))
    """,
    """
    create policy chat_messages_select_own on public.chat_messages
        for select to authenticated
        using (
            exists (
                select 1 from public.chat_threads t
                where t.id = chat_messages.thread_id
                  and t.user_id = (select auth.uid())
            )
        )
    """,
    """
    create policy message_citations_select_own on public.message_citations
        for select to authenticated
        using (
            exists (
                select 1
                from public.chat_messages m
                join public.chat_threads t on t.id = m.thread_id
                where m.id = message_citations.message_id
                  and t.user_id = (select auth.uid())
            )
        )
    """,
)

ALL_TABLES = (
    "users",
    "chat_threads",
    "chat_messages",
    "message_citations",
    "source_documents",
    "document_chunks",
)


def upgrade() -> None:
    """Upgrade schema."""
    # Supabase installs extensions into `extensions`, a stock server into `public`.
    # Pinning the path here means `vector(1536)` below resolves either way.
    op.execute("set local search_path to public, extensions")
    op.execute("create extension if not exists vector")

    op.create_table(
        "source_documents",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("accession_number", sa.String(length=25), nullable=False),
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("form_type", sa.String(length=10), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_documents")),
        sa.UniqueConstraint(
            "accession_number", name=op.f("uq_source_documents_accession_number")
        ),
    )
    op.create_index(
        "ix_source_documents_ticker_fiscal_year",
        "source_documents",
        ["ticker", "fiscal_year"],
        unique=False,
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    # `auth.users` is Supabase's table and must never appear in our metadata, so
    # this edge is written by hand: a profile row cannot outlive its auth user.
    op.create_foreign_key(
        "fk_users_id_auth_users",
        "users",
        "users",
        ["id"],
        ["id"],
        source_schema="public",
        referent_schema="auth",
        ondelete="CASCADE",
    )

    op.create_table(
        "chat_threads",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_threads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_threads")),
    )
    op.create_index(
        "ix_chat_threads_user_id_updated_at",
        "chat_threads",
        ["user_id", sa.literal_column("updated_at DESC")],
        unique=False,
    )

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0", name=op.f("ck_document_chunks_chunk_index_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_documents.id"],
            name=op.f("fk_document_chunks_document_id_source_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name=op.f("uq_document_chunks_document_id_chunk_index"),
        ),
    )
    # Built on an empty table, so this is cheap now and incremental afterwards.
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_document_chunks_metadata",
        "document_chunks",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "user",
                "assistant",
                name="message_role",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            name=op.f("fk_chat_messages_thread_id_chat_threads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
        sa.UniqueConstraint(
            "thread_id", "sequence", name="uq_chat_messages_thread_sequence"
        ),
    )

    op.create_table(
        "message_citations",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("marker", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("form_type", sa.String(length=10), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_message_citations_chunk_id_document_chunks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_documents.id"],
            name=op.f("fk_message_citations_document_id_source_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name=op.f("fk_message_citations_message_id_chat_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_citations")),
        sa.UniqueConstraint(
            "message_id", "marker", name=op.f("uq_message_citations_message_id_marker")
        ),
    )
    op.create_index(
        "ix_message_citations_chunk_id",
        "message_citations",
        ["chunk_id"],
        unique=False,
    )

    for table in ALL_TABLES:
        op.execute(f"alter table public.{table} enable row level security")
    for policy in USER_OWNED_POLICIES:
        op.execute(policy)


def downgrade() -> None:
    """Downgrade schema."""
    # Policies and RLS settings are dropped with their tables. The `vector`
    # extension is left installed: other schemas in the project may rely on it.
    op.drop_index("ix_message_citations_chunk_id", table_name="message_citations")
    op.drop_table("message_citations")
    op.drop_table("chat_messages")
    op.drop_index("ix_document_chunks_search_vector", table_name="document_chunks")
    op.drop_index("ix_document_chunks_metadata", table_name="document_chunks")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_chat_threads_user_id_updated_at", table_name="chat_threads")
    op.drop_table("chat_threads")
    op.drop_table("users")
    op.drop_index(
        "ix_source_documents_ticker_fiscal_year", table_name="source_documents"
    )
    op.drop_table("source_documents")
