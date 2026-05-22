"""Short-term per-topic conversation state.

Used by agents that need multi-turn context — e.g. the Email agent
pending a 'send now?' confirmation, or the Calendar agent waiting on
disambiguation. State is keyed by Telegram `message_thread_id`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from brainbot.db import session_scope
from brainbot.models import ConversationState


async def get_state(thread_id: int) -> dict[str, Any]:
    async with session_scope() as session:
        result = await session.execute(
            select(ConversationState).where(ConversationState.topic_thread_id == thread_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {}
        return {
            "last_intent": dict(row.last_intent or {}),
            "pending_action": dict(row.pending_action or {}),
        }


async def set_state(
    thread_id: int,
    *,
    last_intent: dict[str, Any] | None = None,
    pending_action: dict[str, Any] | None = None,
) -> None:
    async with session_scope() as session:
        result = await session.execute(
            select(ConversationState).where(ConversationState.topic_thread_id == thread_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ConversationState(
                topic_thread_id=thread_id,
                last_intent=last_intent or {},
                pending_action=pending_action or {},
            )
            session.add(row)
        else:
            if last_intent is not None:
                row.last_intent = last_intent
            if pending_action is not None:
                row.pending_action = pending_action


async def clear_pending(thread_id: int) -> None:
    await set_state(thread_id, pending_action={})
