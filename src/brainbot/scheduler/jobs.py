"""APScheduler setup.

In-process scheduler — runs in the same uvicorn worker as the FastAPI
app. For a single-user bot this is fine. If we ever scale up, lift this
into its own service.

Jobs:
- 07:00 SGT every day -> morning briefing
- 22:00 SGT every day -> evening recap
- every minute        -> deliver due todo reminders
"""

from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from brainbot.config import get_settings
from brainbot.db import session_scope
from brainbot.models import ScheduledReminder, Todo
from brainbot.scheduler.evening import run_evening
from brainbot.scheduler.morning import run_morning
from brainbot.telegram.send import escape_md, send_text
from brainbot.telegram.topics import TopicName
from brainbot.utils.logging import get_logger
from brainbot.utils.time import now_utc

log = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def deliver_due_reminders() -> None:
    """Send Telegram messages for any ScheduledReminder whose fire_at has passed."""
    async with session_scope() as session:
        result = await session.execute(
            select(ScheduledReminder)
            .where(
                ScheduledReminder.sent_at.is_(None),
                ScheduledReminder.fire_at <= now_utc(),
            )
            .limit(50)
        )
        due = list(result.scalars())
        if not due:
            return

        for reminder in due:
            todo = await session.get(Todo, reminder.todo_id)
            if todo is None:
                reminder.sent_at = datetime.utcnow()
                continue
            try:
                await send_text(
                    escape_md(f"⏰ Reminder: {todo.content}"),
                    topic=TopicName.TODOS,
                )
            except Exception:
                log.exception("reminder_send_failed", todo_id=todo.id)
                continue
            reminder.sent_at = now_utc()


async def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    tz = get_settings().timezone
    _scheduler = AsyncIOScheduler(timezone=tz)
    _scheduler.add_job(
        run_morning,
        CronTrigger(hour=7, minute=0, timezone=tz),
        id="morning_brief",
        replace_existing=True,
    )
    _scheduler.add_job(
        run_evening,
        CronTrigger(hour=22, minute=0, timezone=tz),
        id="evening_recap",
        replace_existing=True,
    )
    _scheduler.add_job(
        deliver_due_reminders,
        IntervalTrigger(seconds=60),
        id="deliver_reminders",
        replace_existing=True,
    )
    _scheduler.start()
    log.info("scheduler_started", tz=tz)


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("scheduler_stopped")
