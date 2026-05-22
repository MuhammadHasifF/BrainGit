"""FastAPI entrypoint.

Exposes:
- POST /telegram/webhook  — receives Telegram updates
- GET  /healthz            — health probe
- GET  /readyz             — readiness probe (checks DB)

Lifespan starts the APScheduler instance and the LLM client.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from brainbot.config import get_settings
from brainbot.db import engine
from brainbot.telegram.send import send_text
from brainbot.telegram.topics import TopicName
from brainbot.telegram.webhook import (
    is_allowed_user,
    parse_update,
    verify_secret,
)
from brainbot.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info("startup")

    # Scheduler is wired up in Phase 8; import lazily so this module stays
    # importable before that lands.
    try:
        from brainbot.scheduler.jobs import start_scheduler, stop_scheduler

        await start_scheduler()
    except ImportError:
        start_scheduler = stop_scheduler = None  # type: ignore[assignment]

    yield

    if stop_scheduler is not None:
        await stop_scheduler()
    await engine.dispose()
    log.info("shutdown")


app = FastAPI(title="brainbot", lifespan=lifespan)


# ── Simple in-memory token-bucket per IP. Good enough for one user. ────
_RATE_BUCKETS: dict[str, deque[float]] = {}


def _rate_limited(ip: str) -> bool:
    limit = get_settings().webhook_rate_limit_per_minute
    now = time.monotonic()
    window = 60.0
    bucket = _RATE_BUCKETS.setdefault(ip, deque())
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ready"})
    except Exception as exc:
        log.error("readiness_check_failed", error=str(exc))
        return JSONResponse({"status": "unready"}, status_code=503)


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    # 1. Auth: secret header must match.
    if not verify_secret(x_telegram_bot_api_secret_token):
        log.warning("webhook_bad_secret", ip=request.client.host if request.client else "?")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # 2. Rate limit per source IP.
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    # 3. Parse + authorise sender.
    payload = await request.json()
    msg = parse_update(payload)
    if msg is None:
        return {"ok": True, "ignored": "unsupported_update"}

    if not is_allowed_user(msg.user_id):
        log.warning("unauthorised_user", user_id=msg.user_id)
        return {"ok": True, "ignored": "unauthorised"}

    # 4. Dispatch.
    await _dispatch(msg)
    return {"ok": True}


async def _dispatch(msg: Any) -> None:
    """Route the message to the right agent.

    Phase 3 ships an echo handler. Phase 6 replaces this with the real
    `brainbot.agents.router.route(msg)`.
    """
    try:
        from brainbot.agents.router import route  # noqa: PLC0415

        await route(msg)
    except ImportError:
        # Echo fallback so the webhook is testable end-to-end before the
        # agents land.
        topic_label = msg.topic.value if isinstance(msg.topic, TopicName) else str(msg.topic)
        await send_text(
            f"echo \\[{topic_label}\\]: {msg.text}",
            thread_id=msg.thread_id,
            reply_to_message_id=msg.message_id,
        )
