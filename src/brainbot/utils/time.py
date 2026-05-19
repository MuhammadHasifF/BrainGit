"""Timezone helpers. The bot operates in SGT but stores UTC."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from brainbot.config import get_settings

UTC = ZoneInfo("UTC")


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def now_local() -> datetime:
    return datetime.now(tz=local_tz())


def to_local(dt: datetime) -> datetime:
    """Convert any datetime (naive or aware) to local tz."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(local_tz())


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt.astimezone(UTC)


def start_of_day_local(dt: datetime | None = None) -> datetime:
    dt = (dt or now_local()).astimezone(local_tz())
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def end_of_day_local(dt: datetime | None = None) -> datetime:
    return start_of_day_local(dt) + timedelta(days=1) - timedelta(microseconds=1)


def format_local(dt: datetime, fmt: str = "%a %d %b %H:%M") -> str:
    return to_local(dt).strftime(fmt)
