"""Google Calendar connector for the main personal account."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from google.auth.transport.requests import Request as GAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from brainbot.config import get_settings
from brainbot.connectors.oauth_store import load_token, save_token
from brainbot.utils.logging import get_logger
from brainbot.utils.time import to_utc

log = get_logger(__name__)

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


@dataclass(slots=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None
    description: str | None


async def _credentials(account_label: str) -> Credentials:
    settings = get_settings()
    token = await load_token(account_label=account_label, provider="google")
    if token is None:
        raise RuntimeError(
            f"No Google credentials for account {account_label!r}. "
            "Run `python scripts/auth_google.py` first."
        )
    creds = Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=token.scopes or CALENDAR_SCOPES,
    )
    if not creds.valid:
        await asyncio.to_thread(creds.refresh, GAuthRequest())
        await save_token(
            account_label=account_label,
            provider="google",
            refresh_token=creds.refresh_token or token.refresh_token,
            access_token=creds.token,
            expires_at=creds.expiry.replace(tzinfo=None) if creds.expiry else None,
            scopes=list(creds.scopes or token.scopes),
        )
    return creds


async def _service(account_label: str) -> Any:
    creds = await _credentials(account_label)
    return await asyncio.to_thread(
        build, "calendar", "v3", credentials=creds, cache_discovery=False
    )


async def list_events(
    account_label: str, *, start: datetime, end: datetime, calendar_id: str = "primary"
) -> list[CalendarEvent]:
    svc = await _service(account_label)
    listing = await asyncio.to_thread(
        lambda: svc.events()
        .list(
            calendarId=calendar_id,
            timeMin=to_utc(start).isoformat(),
            timeMax=to_utc(end).isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    out: list[CalendarEvent] = []
    for item in listing.get("items", []):
        s = item["start"].get("dateTime") or item["start"].get("date")
        e = item["end"].get("dateTime") or item["end"].get("date")
        out.append(
            CalendarEvent(
                id=item["id"],
                title=item.get("summary", "(no title)"),
                start=datetime.fromisoformat(s.replace("Z", "+00:00")),
                end=datetime.fromisoformat(e.replace("Z", "+00:00")),
                location=item.get("location"),
                description=item.get("description"),
            )
        )
    return out


async def create_event(
    account_label: str,
    *,
    title: str,
    start: datetime,
    end: datetime,
    description: str | None = None,
    location: str | None = None,
    calendar_id: str = "primary",
) -> str:
    svc = await _service(account_label)
    body = {
        "summary": title,
        "description": description,
        "location": location,
        "start": {"dateTime": to_utc(start).isoformat()},
        "end": {"dateTime": to_utc(end).isoformat()},
    }
    created = await asyncio.to_thread(
        lambda: svc.events().insert(calendarId=calendar_id, body=body).execute()
    )
    return created["id"]


async def update_event(
    account_label: str,
    event_id: str,
    *,
    title: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    calendar_id: str = "primary",
) -> None:
    svc = await _service(account_label)
    patch: dict[str, Any] = {}
    if title is not None:
        patch["summary"] = title
    if start is not None:
        patch["start"] = {"dateTime": to_utc(start).isoformat()}
    if end is not None:
        patch["end"] = {"dateTime": to_utc(end).isoformat()}
    await asyncio.to_thread(
        lambda: svc.events().patch(calendarId=calendar_id, eventId=event_id, body=patch).execute()
    )


async def delete_event(account_label: str, event_id: str, *, calendar_id: str = "primary") -> None:
    svc = await _service(account_label)
    await asyncio.to_thread(
        lambda: svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    )
