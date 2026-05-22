"""Morning briefing job — runs at 07:00 SGT."""

from __future__ import annotations

from brainbot.agents.routine_agent import compose_morning
from brainbot.telegram.send import escape_md, send_text
from brainbot.telegram.topics import TopicName
from brainbot.utils.logging import get_logger

log = get_logger(__name__)


async def run_morning() -> None:
    log.info("morning_brief_start")
    try:
        text = await compose_morning()
        await send_text(escape_md(text), topic=TopicName.DAILY_ROUTINE)
        log.info("morning_brief_sent")
    except Exception:
        log.exception("morning_brief_failed")
