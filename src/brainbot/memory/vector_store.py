"""pgvector-backed semantic memory for the second brain.

Notes are stored in `notes`; one `note_embeddings` row per note holds
the Gemini embedding. Search is cosine-distance ANN via the IVFFlat
index.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from brainbot.db import session_scope
from brainbot.memory.embeddings import embed_text
from brainbot.models import Note, NoteEmbedding
from brainbot.utils.logging import get_logger
from brainbot.utils.time import to_utc

log = get_logger(__name__)


@dataclass(slots=True)
class StoredNote:
    id: int
    content: str
    tags: list[str]
    source_topic: str | None
    created_at: datetime
    similarity: float | None = None


async def save_note(
    content: str, *, tags: list[str] | None = None, source_topic: str | None = None
) -> StoredNote:
    embedding = await embed_text(content)
    async with session_scope() as session:
        note = Note(content=content, tags=tags or [], source_topic=source_topic)
        session.add(note)
        await session.flush()
        session.add(NoteEmbedding(note_id=note.id, embedding=embedding))
        return StoredNote(
            id=note.id,
            content=note.content,
            tags=list(note.tags or []),
            source_topic=note.source_topic,
            created_at=note.created_at,
        )


async def semantic_search(
    query: str, *, limit: int = 10, since: datetime | None = None, until: datetime | None = None
) -> list[StoredNote]:
    query_vec = await embed_text(query)
    async with session_scope() as session:
        # `<=>` is cosine distance in pgvector; smaller = more similar.
        stmt = (
            select(
                Note,
                NoteEmbedding.embedding.cosine_distance(query_vec).label("dist"),
            )
            .join(NoteEmbedding, NoteEmbedding.note_id == Note.id)
        )
        if since is not None:
            stmt = stmt.where(Note.created_at >= to_utc(since))
        if until is not None:
            stmt = stmt.where(Note.created_at <= to_utc(until))
        stmt = stmt.order_by("dist").limit(limit)
        result = await session.execute(stmt)
        out: list[StoredNote] = []
        for note, dist in result.all():
            out.append(
                StoredNote(
                    id=note.id,
                    content=note.content,
                    tags=list(note.tags or []),
                    source_topic=note.source_topic,
                    created_at=note.created_at,
                    similarity=1.0 - float(dist),
                )
            )
        return out


async def notes_in_range(
    *, since: datetime, until: datetime, tag: str | None = None
) -> list[StoredNote]:
    """Plain date-range query without embeddings — for 'what did I write last week'."""
    async with session_scope() as session:
        stmt = (
            select(Note)
            .where(Note.created_at >= to_utc(since), Note.created_at <= to_utc(until))
            .order_by(Note.created_at.desc())
        )
        if tag:
            stmt = stmt.where(Note.tags.contains([tag]))
        result = await session.execute(stmt)
        return [
            StoredNote(
                id=n.id,
                content=n.content,
                tags=list(n.tags or []),
                source_topic=n.source_topic,
                created_at=n.created_at,
            )
            for n in result.scalars()
        ]


def to_dict(note: StoredNote) -> dict[str, Any]:
    return {
        "id": note.id,
        "content": note.content,
        "tags": note.tags,
        "source_topic": note.source_topic,
        "created_at": note.created_at.isoformat(),
        "similarity": note.similarity,
    }
