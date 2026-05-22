"""Microsoft Graph calendar connector (school account)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from brainbot.connectors.outlook import _request
from brainbot.utils.time import to_utc


@dataclass(slots=True)
class OutlookEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None
    body_preview: str | None


def _parse_dt(value: dict[str, Any]) -> datetime:
    # Graph returns "2026-01-01T09:00:00.0000000" + a `timeZone` field.
    raw = value.get("dateTime", "")
    if "." in raw:
        raw = raw.split(".", 1)[0]
    dt = datetime.fromisoformat(raw)
    # Treat as UTC if no offset present; Graph returns UTC by default.
    if dt.tzinfo is None:
        return dt.replace(tzinfo=__import__("datetime").timezone.utc)
    return dt


async def list_events(*, start: datetime, end: datetime) -> list[OutlookEvent]:
    params = {
        "startDateTime": to_utc(start).isoformat(),
        "endDateTime": to_utc(end).isoformat(),
        "$orderby": "start/dateTime",
        "$top": "100",
    }
    data = await _request("GET", "/me/calendarView", params=params) or {}
    out: list[OutlookEvent] = []
    for item in data.get("value", []):
        loc = item.get("location", {}).get("displayName") if item.get("location") else None
        out.append(
            OutlookEvent(
                id=item["id"],
                title=item.get("subject", "(no title)"),
                start=_parse_dt(item["start"]),
                end=_parse_dt(item["end"]),
                location=loc or None,
                body_preview=item.get("bodyPreview"),
            )
        )
    return out


async def create_event(
    *,
    title: str,
    start: datetime,
    end: datetime,
    description: str | None = None,
    location: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "subject": title,
        "start": {"dateTime": to_utc(start).isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": to_utc(end).isoformat(), "timeZone": "UTC"},
    }
    if description:
        payload["body"] = {"contentType": "Text", "content": description}
    if location:
        payload["location"] = {"displayName": location}
    created = await _request("POST", "/me/events", json=payload)
    return str(created["id"])


async def update_event(
    event_id: str,
    *,
    title: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> None:
    patch: dict[str, Any] = {}
    if title is not None:
        patch["subject"] = title
    if start is not None:
        patch["start"] = {"dateTime": to_utc(start).isoformat(), "timeZone": "UTC"}
    if end is not None:
        patch["end"] = {"dateTime": to_utc(end).isoformat(), "timeZone": "UTC"}
    if patch:
        await _request("PATCH", f"/me/events/{event_id}", json=patch)


async def delete_event(event_id: str) -> None:
    await _request("DELETE", f"/me/events/{event_id}")
