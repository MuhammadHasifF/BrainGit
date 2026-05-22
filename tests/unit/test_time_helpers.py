from __future__ import annotations

from datetime import datetime, timedelta, timezone

from brainbot.utils.time import (
    end_of_day_local,
    local_tz,
    start_of_day_local,
    to_local,
    to_utc,
)


def test_local_tz_is_sgt() -> None:
    assert str(local_tz()) == "Asia/Singapore"


def test_to_local_converts_utc() -> None:
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    local = to_local(dt)
    # SGT = UTC+8
    assert local.hour == 20


def test_to_utc_assumes_local_when_naive() -> None:
    naive_local = datetime(2026, 1, 1, 12, 0)  # treated as SGT
    utc = to_utc(naive_local)
    assert utc.hour == 4
    assert utc.tzinfo is not None


def test_start_and_end_of_day_bound_24h() -> None:
    start = start_of_day_local()
    end = end_of_day_local()
    assert (end - start) < timedelta(days=1)
    assert (end - start) > timedelta(hours=23, minutes=59)
