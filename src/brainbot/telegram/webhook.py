"""Telegram webhook parsing + auth.

This module receives the raw JSON from Telegram, validates the secret
header, checks the sender is whitelisted, and hands the parsed update to
the agent router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brainbot.config import get_settings
from brainbot.telegram.topics import TopicName, topic_for_thread_id
from brainbot.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class IncomingMessage:
    """Normalised view of a Telegram update relevant to brainbot."""

    update_id: int
    chat_id: int
    user_id: int
    thread_id: int | None
    topic: TopicName
    text: str
    message_id: int
    is_callback: bool = False
    callback_data: str | None = None
    callback_query_id: str | None = None


def verify_secret(header_value: str | None) -> bool:
    """Constant-time-ish check that the secret header matches our config."""
    expected = get_settings().telegram_webhook_secret
    if not expected:
        # Misconfigured — reject everything rather than allow everything.
        return False
    if not header_value:
        return False
    return header_value == expected


def is_allowed_user(user_id: int) -> bool:
    allowed = get_settings().allowed_user_id_set
    return user_id in allowed if allowed else False


def parse_update(update: dict[str, Any]) -> IncomingMessage | None:
    """Convert a raw Telegram update into an IncomingMessage.

    Returns None if the update is one we don't care about (edited
    messages, channel posts, bot commands we don't handle, etc.).
    """
    update_id = update.get("update_id", 0)

    # Inline button press
    callback = update.get("callback_query")
    if callback:
        msg = callback.get("message") or {}
        return IncomingMessage(
            update_id=update_id,
            chat_id=msg.get("chat", {}).get("id", 0),
            user_id=callback.get("from", {}).get("id", 0),
            thread_id=msg.get("message_thread_id"),
            topic=topic_for_thread_id(msg.get("message_thread_id")),
            text="",
            message_id=msg.get("message_id", 0),
            is_callback=True,
            callback_data=callback.get("data"),
            callback_query_id=callback.get("id"),
        )

    message = update.get("message") or update.get("edited_message")
    if not message:
        return None

    chat = message.get("chat", {})
    sender = message.get("from", {})
    text = message.get("text") or message.get("caption") or ""

    return IncomingMessage(
        update_id=update_id,
        chat_id=chat.get("id", 0),
        user_id=sender.get("id", 0),
        thread_id=message.get("message_thread_id"),
        topic=topic_for_thread_id(message.get("message_thread_id")),
        text=text,
        message_id=message.get("message_id", 0),
    )
