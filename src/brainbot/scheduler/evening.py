"""Evening recap job — runs at 22:00 SGT."""

from __future__ import annotations

from brainbot.agents.routine_agent import compose_evening
from brainbot.telegram.send import escape_md, send_text
from brainbot.telegram.topics import TopicName
from brainbot.utils.logging import get_logger

log = get_logger(__name__)


async def run_evening() -> None:
    log.info("evening_recap_start")
    try:
        text = await compose_evening()
        await send_text(escape_md(text), topic=TopicName.EVENING_RECAP)
        log.info("evening_recap_sent")
    except Exception:
        log.exception("evening_recap_failed")
