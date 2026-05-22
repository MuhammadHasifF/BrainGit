"""Routine agent — composes the morning brief + evening recap.

Unlike the user-facing agents, this one is called by the scheduler. It
gathers raw data via the connectors and the todo store, hands it to
Gemini with a "compose a Markdown brief" prompt, and returns text the
scheduler posts to the Daily Routine / Evening Recap topic.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, select

from brainbot.config import get_settings
from brainbot.connectors import gmail, google_calendar, outlook, outlook_calendar
from brainbot.db import session_scope
from brainbot.llm.client import get_llm
from brainbot.models import Todo
from brainbot.utils.logging import get_logger
from brainbot.utils.time import (
    end_of_day_local,
    now_local,
    now_utc,
    start_of_day_local,
    to_utc,
)

log = get_logger(__name__)


# DESIGN NOTE: senders flagged "urgent" are configured by tag elsewhere later;
# for now we just surface unread mail and let the LLM decide what's urgent.
URGENT_QUERY_GMAIL = "is:unread newer_than:1d"
URGENT_QUERY_OUTLOOK = "isRead eq false"


async def _gather_morning() -> dict[str, Any]:
    today_start = start_of_day_local()
    today_end = end_of_day_local()

    # Calendars
    try:
        g_events = await google_calendar.list_events("main", start=today_start, end=today_end)
    except Exception as exc:  # noqa: BLE001
        log.warning("morning_gcal_failed", error=str(exc))
        g_events = []
    try:
        o_events = await outlook_calendar.list_events(start=today_start, end=today_end)
    except Exception as exc:  # noqa: BLE001
        log.warning("morning_outlook_cal_failed", error=str(exc))
        o_events = []

    # Mail
    mail_summaries: list[dict[str, Any]] = []
    for label in get_settings().google_account_label_list:
        try:
            msgs = await gmail.list_messages(label, query=URGENT_QUERY_GMAIL, max_results=10)
            mail_summaries.extend({"account": label, **vars(m)} for m in msgs)
        except Exception as exc:  # noqa: BLE001
            log.warning("morning_gmail_failed", account=label, error=str(exc))
    try:
        ms_msgs = await outlook.list_messages(query=URGENT_QUERY_OUTLOOK, top=10)
        mail_summaries.extend({"account": "school", **vars(m)} for m in ms_msgs)
    except Exception as exc:  # noqa: BLE001
        log.warning("morning_outlook_failed", error=str(exc))

    # Todos due today
    async with session_scope() as session:
        result = await session.execute(
            select(Todo).where(
                Todo.status == "open",
                or_(Todo.due_at.is_(None), Todo.due_at <= to_utc(today_end)),
            )
        )
        todos = [
            {"id": t.id, "content": t.content, "due_at": t.due_at.isoformat() if t.due_at else None}
            for t in result.scalars()
        ]

    return {
        "date": now_local().strftime("%A %d %b %Y"),
        "events_main": [vars(e) for e in g_events],
        "events_school": [vars(e) for e in o_events],
        "urgent_mail": mail_summaries,
        "todos": todos,
    }


async def _gather_evening() -> dict[str, Any]:
    today_start = start_of_day_local()
    today_end = end_of_day_local()
    tomorrow_start = today_start + timedelta(days=1)
    tomorrow_end = today_end + timedelta(days=1)

    async with session_scope() as session:
        # Completed today
        completed = await session.execute(
            select(Todo).where(
                Todo.status == "completed",
                Todo.completed_at >= to_utc(today_start),
                Todo.completed_at <= to_utc(today_end),
            )
        )
        completed_list = [{"id": t.id, "content": t.content} for t in completed.scalars()]

        # Overdue / missed
        overdue = await session.execute(
            select(Todo).where(
                Todo.status == "open",
                Todo.due_at.is_not(None),
                Todo.due_at < now_utc(),
            )
        )
        overdue_list = [
            {"id": t.id, "content": t.content, "due_at": t.due_at.isoformat() if t.due_at else None}
            for t in overdue.scalars()
        ]

        # Due tomorrow
        tomorrow = await session.execute(
            select(Todo).where(
                Todo.status == "open",
                and_(Todo.due_at >= to_utc(tomorrow_start), Todo.due_at <= to_utc(tomorrow_end)),
            )
        )
        tomorrow_todos = [
            {"id": t.id, "content": t.content} for t in tomorrow.scalars()
        ]

    # Tomorrow's calendar
    try:
        g_tomorrow = await google_calendar.list_events("main", start=tomorrow_start, end=tomorrow_end)
    except Exception:
        g_tomorrow = []
    try:
        o_tomorrow = await outlook_calendar.list_events(start=tomorrow_start, end=tomorrow_end)
    except Exception:
        o_tomorrow = []

    return {
        "date": now_local().strftime("%A %d %b %Y"),
        "completed": completed_list,
        "overdue": overdue_list,
        "tomorrow_events_main": [vars(e) for e in g_tomorrow],
        "tomorrow_events_school": [vars(e) for e in o_tomorrow],
        "tomorrow_todos": tomorrow_todos,
    }


# ── Compose ────────────────────────────────────────────────────────────

MORNING_PROMPT = """Compose a concise morning briefing in Markdown for the user.
Structure:
1. *Today's date* — one line.
2. *Calendar* — bullet today's events from both calendars, time + title.
3. *Mail* — bullet up to 5 most urgent unread emails (sender + subject).
   If nothing important, say "Nothing urgent".
4. *Todos* — bullet open todos due today.
5. *One-line vibe check* — friendly closing line.

Use bold for section headers. No emoji. Singapore time. Be terse.
"""

EVENING_PROMPT = """Compose a concise evening recap in Markdown.
Structure:
1. *Wins today* — bullet completed todos.
2. *Missed* — bullet overdue todos (or "All caught up").
3. *Tomorrow* — bullet tomorrow's events + todos.
4. *One-line reflection prompt* — a single question.

Use bold for section headers. No emoji. Be terse.
"""


async def compose_morning() -> str:
    data = await _gather_morning()
    result = await get_llm().generate(
        prompt=f"Data:\n{data!r}\n\n{MORNING_PROMPT}",
        smart=False,
    )
    return result.text.strip() or "(empty)"


async def compose_evening() -> str:
    data = await _gather_evening()
    result = await get_llm().generate(
        prompt=f"Data:\n{data!r}\n\n{EVENING_PROMPT}",
        smart=False,
    )
    return result.text.strip() or "(empty)"
