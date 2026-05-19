"""ORM models for brainbot.

Conventions:
- Timestamps are timezone-aware UTC.
- Free-form labels use JSONB to avoid migrations every time we tweak tags.
- Encrypted columns are LargeBinary; encryption/decryption lives in
  `brainbot.connectors.oauth_store`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from brainbot.db import Base

# DESIGN NOTE: Gemini's text-embedding-004 returns 768-dimensional vectors.
EMBEDDING_DIM = 768


class AccountToken(Base):
    """OAuth credentials per (provider, account_label)."""

    __tablename__ = "account_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_label: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)  # "google" | "microsoft"
    encrypted_refresh_token: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_access_token: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    recurring_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # iCalendar RRULE string e.g. "FREQ=DAILY;BYHOUR=9"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    reminders: Mapped[list["ScheduledReminder"]] = relationship(
        back_populates="todo", cascade="all, delete-orphan"
    )


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_topic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    embeddings: Mapped[list["NoteEmbedding"]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )


class NoteEmbedding(Base):
    __tablename__ = "note_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), index=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    note: Mapped["Note"] = relationship(back_populates="embeddings")


class EmailSummaryCache(Base):
    """Avoid re-summarising the same email twice."""

    __tablename__ = "email_summaries_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_label: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[str] = mapped_column(String(255), index=True)
    summary: Mapped[str] = mapped_column(Text)
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConversationState(Base):
    """Short-term per-topic state so multi-turn flows survive across messages."""

    __tablename__ = "conversation_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_thread_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    last_intent: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    pending_action: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ScheduledReminder(Base):
    __tablename__ = "scheduled_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    todo_id: Mapped[int] = mapped_column(
        ForeignKey("todos.id", ondelete="CASCADE"), index=True
    )
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    todo: Mapped["Todo"] = relationship(back_populates="reminders")
