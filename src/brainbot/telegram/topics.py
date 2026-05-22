"""Topic identifiers and routing.

The bot uses one Telegram group with Topics enabled. Each topic is mapped
to an "agent name" so the router can dispatch the right handler.
"""

from __future__ import annotations

from enum import Enum

from brainbot.config import get_settings


class TopicName(str, Enum):
    DAILY_ROUTINE = "daily_routine"
    EVENING_RECAP = "evening_recap"
    EMAILS = "emails"
    CALENDAR = "calendar"
    TODOS = "todos"
    SECOND_BRAIN = "second_brain"
    QUICK_NOTES = "quick_notes"
    GENERAL = "general"


# Topics that are push-only (bot writes, doesn't run command parsing).
PUSH_ONLY = {TopicName.DAILY_ROUTINE, TopicName.EVENING_RECAP}


def topic_for_thread_id(thread_id: int | None) -> TopicName:
    """Resolve a message's `message_thread_id` to a TopicName.

    Falls back to GENERAL for unknown threads (including when topics are
    disabled and thread_id is None).
    """
    if thread_id is None:
        return TopicName.GENERAL

    mapping = get_settings().topic_map  # thread_id -> str
    name = mapping.get(thread_id)
    if name is None:
        return TopicName.GENERAL
    return TopicName(name)


def thread_id_for_topic(topic: TopicName) -> int | None:
    """Inverse of `topic_for_thread_id` — returns the configured thread id, if any."""
    settings = get_settings()
    by_name = {
        TopicName.DAILY_ROUTINE: settings.topic_daily_routine,
        TopicName.EVENING_RECAP: settings.topic_evening_recap,
        TopicName.EMAILS: settings.topic_emails,
        TopicName.CALENDAR: settings.topic_calendar,
        TopicName.TODOS: settings.topic_todos,
        TopicName.SECOND_BRAIN: settings.topic_second_brain,
        TopicName.QUICK_NOTES: settings.topic_quick_notes,
        TopicName.GENERAL: settings.topic_general,
    }
    tid = by_name[topic]
    return tid or None
