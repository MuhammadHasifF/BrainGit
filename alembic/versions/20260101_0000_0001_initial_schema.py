"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    # pgvector extension must exist before we can create vector columns.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_label", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("encrypted_refresh_token", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_access_token", sa.LargeBinary(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_account_tokens_account_label", "account_tokens", ["account_label"])
    op.create_index("ix_account_tokens_provider", "account_tokens", ["provider"])

    op.create_table(
        "todos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "tags",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("recurring_rule", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_todos_status", "todos", ["status"])

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tags",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("source_topic", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notes_created_at", "notes", ["created_at"])

    op.create_table(
        "note_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "note_id",
            sa.Integer(),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
    )
    op.create_index("ix_note_embeddings_note_id", "note_embeddings", ["note_id"])
    # IVFFlat index — good enough at our scale, builds quickly.
    op.execute(
        "CREATE INDEX ix_note_embeddings_vec ON note_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "email_summaries_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_label", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_email_summaries_cache_account_message",
        "email_summaries_cache",
        ["account_label", "message_id"],
        unique=True,
    )

    op.create_table(
        "conversation_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_thread_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "last_intent",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "pending_action",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_conversation_state_topic", "conversation_state", ["topic_thread_id"], unique=True
    )

    op.create_table(
        "scheduled_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "todo_id",
            sa.Integer(),
            sa.ForeignKey("todos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scheduled_reminders_todo_id", "scheduled_reminders", ["todo_id"])
    op.create_index("ix_scheduled_reminders_fire_at", "scheduled_reminders", ["fire_at"])


def downgrade() -> None:
    op.drop_table("scheduled_reminders")
    op.drop_table("conversation_state")
    op.drop_table("email_summaries_cache")
    op.drop_table("note_embeddings")
    op.drop_table("notes")
    op.drop_table("todos")
    op.drop_table("account_tokens")
    # Don't drop the vector extension — other dbs in the cluster may need it.
