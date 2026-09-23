"""chat_messages touch parent thread

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22

Migration 0002 moves `chat_threads.updated_at` on every update of that table,
but a new message is an insert into `chat_messages` and touches nothing. So a
thread that has been used all afternoon still sorts by the moment it was
created, and `ix_chat_threads_user_id_updated_at` — which the sidebar orders on
— keeps reporting "newest thread first" instead of "most recent activity".

Same reasoning as 0002: a trigger is the only place the rule holds for every
writer, and it cannot be inferred from the models by autogenerate. Updating
`chat_threads` inserts no messages, so the two triggers cannot recurse.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # `set search_path = ''` for the same reason as 0002: nothing in the body
    # may resolve through a caller-controlled path, so every name is qualified.
    # The assignment is what matters, not the value — 0002's `before update`
    # trigger on `chat_threads` overwrites it with its own `now()`.
    op.execute("""
        create or replace function public.touch_thread_on_message()
        returns trigger
        language plpgsql
        set search_path = ''
        as $$
        begin
            update public.chat_threads
                set updated_at = now()
                where id = new.thread_id;
            return null;
        end;
        $$
    """)
    # `after insert`: the parent row is bumped once the message is actually
    # stored, and the trigger's return value is ignored, so it cannot alter it.
    op.execute("""
        create trigger chat_messages_touch_thread
            after insert on public.chat_messages
            for each row
            execute function public.touch_thread_on_message()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "drop trigger if exists chat_messages_touch_thread on public.chat_messages"
    )
    op.execute("drop function if exists public.touch_thread_on_message()")
