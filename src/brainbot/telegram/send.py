"""Outbound Telegram messages.

A single shared `Bot` instance is created lazily. All outgoing message
helpers accept a `topic` argument so the message lands in the right
thread.
"""

from __future__ import annotations

from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from brainbot.config import get_settings
from brainbot.telegram.topics import TopicName, thread_id_for_topic
from brainbot.utils.logging import get_logger

log = get_logger(__name__)

_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=get_settings().telegram_bot_token)
    return _bot


async def send_text(
    text: str,
    *,
    topic: TopicName | None = None,
    thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    buttons: list[list[tuple[str, str]]] | None = None,
    parse_mode: str | None = ParseMode.MARKDOWN_V2,
) -> int:
    """Send a text message. Returns the resulting message_id.

    Either `topic` or `thread_id` may be supplied; `topic` is resolved via
    the configured topic map. `buttons` is a list of rows; each row is a
    list of (label, callback_data) tuples.
    """
    settings = get_settings()
    chat_id = settings.telegram_group_chat_id
    if thread_id is None and topic is not None:
        thread_id = thread_id_for_topic(topic)

    markup: InlineKeyboardMarkup | None = None
    if buttons:
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=lbl, callback_data=data) for lbl, data in row]
             for row in buttons]
        )

    msg = await get_bot().send_message(
        chat_id=chat_id,
        text=text,
        message_thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
        parse_mode=parse_mode,
        reply_markup=markup,
        disable_web_page_preview=True,
    )
    log.info("sent_message", thread_id=thread_id, message_id=msg.message_id)
    return msg.message_id


async def answer_callback(callback_query_id: str, text: str | None = None) -> None:
    """Acknowledge an inline-button press."""
    await get_bot().answer_callback_query(callback_query_id=callback_query_id, text=text)


async def edit_message(
    *,
    chat_id: int,
    message_id: int,
    text: str,
    parse_mode: str | None = ParseMode.MARKDOWN_V2,
) -> None:
    await get_bot().edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )


def escape_md(text: str) -> str:
    """Escape text for Telegram MarkdownV2.

    Telegram's MarkdownV2 requires literal `_*[]()~\\`>#+-=|{}.!` to be
    escaped with a backslash.
    """
    chars = r"_*[]()~`>#+-=|{}.!\\"
    out: list[str] = []
    for ch in text:
        if ch in chars:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def confirmation_buttons(action_id: str) -> list[list[tuple[str, str]]]:
    """Standard yes/no inline keyboard. callback_data is `action_id:yes` / `:no`."""
    return [[("✅ Yes", f"{action_id}:yes"), ("❌ No", f"{action_id}:no")]]


def kwargs_or_none(d: dict[str, Any]) -> dict[str, Any]:
    """Drop None values — handy for building Bot kwargs."""
    return {k: v for k, v in d.items() if v is not None}
