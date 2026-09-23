"""chat_threads updated_at trigger

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22

`ChatThread.updated_at` is declared with SQLAlchemy's `onupdate`, which is
applied in Python by the ORM. Every write in this service goes through
PostgREST, so the column never actually moved off its insert value — and
`ix_chat_threads_user_id_updated_at` orders the thread list on it, so "most
recent activity first" silently meant "newest thread first".

A trigger is the only place the rule holds for every writer, and — like the RLS
policies and the `auth.users` foreign key in 0001 — it is something autogenerate
cannot infer from the models.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # An empty `search_path` keeps the function from resolving anything through
    # a caller-controlled path; `now()` lives in `pg_catalog`, which is always
    # searched. Supabase's linter flags functions that leave it mutable.
    op.execute("""
        create or replace function public.set_updated_at()
        returns trigger
        language plpgsql
        set search_path = ''
        as $$
        begin
            new.updated_at = now();
            return new;
        end;
        $$
    """)
    op.execute("""
        create trigger chat_threads_set_updated_at
            before update on public.chat_threads
            for each row
            execute function public.set_updated_at()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "drop trigger if exists chat_threads_set_updated_at on public.chat_threads"
    )
    op.execute("drop function if exists public.set_updated_at()")
