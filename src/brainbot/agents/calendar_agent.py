"""Calendar agent — Google Calendar (main) + Outlook Calendar (school).

Handles natural-language event creation ("gym tmrw 7-8pm"), conflict
detection across both calendars, and free-slot search. We use the
smart model here because date/time disambiguation benefits from it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from dateutil import parser as dateparser

from brainbot.agents.base import BaseAgent
from brainbot.connectors import google_calendar, outlook_calendar
from brainbot.llm.tools import Tool, schema_object, schema_string
from brainbot.utils.time import end_of_day_local, local_tz, now_local, start_of_day_local


class CalendarAgent(BaseAgent):
    name = "calendar"
    smart = True
    system_prompt = (
        "You are the Calendar agent. The user has two calendars: 'main' (Google) and "
        "'school' (Outlook). When the user asks about 'today' or 'this week', query "
        "both calendars and merge results. When creating events, infer the calendar "
        "from context (e.g. lecture/tutorial -> school, gym/personal -> main). "
        "Always confirm time zone is Singapore (SGT, UTC+8) unless told otherwise. "
        "Before deleting an event, repeat the title + time and ask for confirmation."
    )

    def register_tools(self) -> None:
        self.tools.add(Tool(
            name="list_events",
            description="List events from one or both calendars within a date range.",
            parameters=schema_object(
                {
                    "calendar": schema_string(
                        "'main', 'school', or 'both'.", enum=["main", "school", "both"]
                    ),
                    "start": schema_string(
                        "ISO 8601 start, or natural language ('today', 'tomorrow 9am')."
                    ),
                    "end": schema_string(
                        "ISO 8601 end, or natural language ('end of week')."
                    ),
                },
                required=["calendar", "start", "end"],
            ),
            handler=_list_events,
        ))

        self.tools.add(Tool(
            name="create_event",
            description="Create a calendar event.",
            parameters=schema_object(
                {
                    "calendar": schema_string("'main' or 'school'.", enum=["main", "school"]),
                    "title": schema_string("Event title."),
                    "start": schema_string("ISO 8601 or natural language."),
                    "end": schema_string("ISO 8601 or natural language."),
                    "description": schema_string("Optional description / agenda."),
                    "location": schema_string("Optional location."),
                },
                required=["calendar", "title", "start", "end"],
            ),
            handler=_create_event,
        ))

        self.tools.add(Tool(
            name="update_event",
            description="Change an event's title, start, or end.",
            parameters=schema_object(
                {
                    "calendar": schema_string("'main' or 'school'.", enum=["main", "school"]),
                    "event_id": schema_string("Provider event id."),
                    "title": schema_string("New title (optional)."),
                    "start": schema_string("New start (optional)."),
                    "end": schema_string("New end (optional)."),
                },
                required=["calendar", "event_id"],
            ),
            handler=_update_event,
        ))

        self.tools.add(Tool(
            name="delete_event",
            description="Delete an event by id.",
            parameters=schema_object(
                {
                    "calendar": schema_string("'main' or 'school'.", enum=["main", "school"]),
                    "event_id": schema_string("Provider event id."),
                },
                required=["calendar", "event_id"],
            ),
            handler=_delete_event,
        ))

        self.tools.add(Tool(
            name="find_free_slots",
            description=(
                "Find free time slots across both calendars within a window. "
                "Returns blocks at least `min_minutes` long."
            ),
            parameters=schema_object(
                {
                    "start": schema_string("Window start."),
                    "end": schema_string("Window end."),
                    "min_minutes": {"type": "integer", "description": "Default 30."},
                },
                required=["start", "end"],
            ),
            handler=_find_free_slots,
        ))


# ── Helpers ────────────────────────────────────────────────────────────

def _parse(when: str, *, default: datetime | None = None) -> datetime:
    """Loose datetime parser. Accepts ISO + natural-ish strings."""
    text = when.strip().lower()
    today = start_of_day_local()
    shortcuts = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "tmrw": today + timedelta(days=1),
        "yesterday": today - timedelta(days=1),
        "now": now_local(),
        "end of day": end_of_day_local(),
        "end of week": today + timedelta(days=(6 - today.weekday())),
    }
    if text in shortcuts:
        return shortcuts[text]
    return dateparser.parse(when, default=default or now_local(), fuzzy=True).replace(
        tzinfo=local_tz()
    )


# ── Tool handlers ──────────────────────────────────────────────────────

async def _list_events(args: dict[str, Any]) -> list[dict[str, Any]]:
    start = _parse(args["start"])
    end = _parse(args["end"], default=start)
    out: list[dict[str, Any]] = []

    if args["calendar"] in ("main", "both"):
        events = await google_calendar.list_events("main", start=start, end=end)
        out.extend({"calendar": "main", **vars(e)} for e in events)
    if args["calendar"] in ("school", "both"):
        events = await outlook_calendar.list_events(start=start, end=end)
        out.extend({"calendar": "school", **vars(e)} for e in events)
    return out


async def _create_event(args: dict[str, Any]) -> dict[str, str]:
    start = _parse(args["start"])
    end = _parse(args["end"], default=start + timedelta(hours=1))
    if args["calendar"] == "main":
        eid = await google_calendar.create_event(
            "main",
            title=args["title"],
            start=start,
            end=end,
            description=args.get("description"),
            location=args.get("location"),
        )
    else:
        eid = await outlook_calendar.create_event(
            title=args["title"],
            start=start,
            end=end,
            description=args.get("description"),
            location=args.get("location"),
        )
    return {"event_id": eid, "status": "created"}


async def _update_event(args: dict[str, Any]) -> dict[str, str]:
    start = _parse(args["start"]) if args.get("start") else None
    end = _parse(args["end"]) if args.get("end") else None
    if args["calendar"] == "main":
        await google_calendar.update_event(
            "main",
            args["event_id"],
            title=args.get("title"),
            start=start,
            end=end,
        )
    else:
        await outlook_calendar.update_event(
            args["event_id"],
            title=args.get("title"),
            start=start,
            end=end,
        )
    return {"status": "updated"}


async def _delete_event(args: dict[str, Any]) -> dict[str, str]:
    if args["calendar"] == "main":
        await google_calendar.delete_event("main", args["event_id"])
    else:
        await outlook_calendar.delete_event(args["event_id"])
    return {"status": "deleted"}


async def _find_free_slots(args: dict[str, Any]) -> list[dict[str, str]]:
    start = _parse(args["start"])
    end = _parse(args["end"], default=start + timedelta(days=1))
    min_minutes = int(args.get("min_minutes", 30))

    g = await google_calendar.list_events("main", start=start, end=end)
    o = await outlook_calendar.list_events(start=start, end=end)
    busy = sorted(
        [(e.start, e.end) for e in g] + [(e.start, e.end) for e in o],
        key=lambda x: x[0],
    )

    slots: list[dict[str, str]] = []
    cursor = start
    for bstart, bend in busy:
        if bstart > cursor and (bstart - cursor) >= timedelta(minutes=min_minutes):
            slots.append({"start": cursor.isoformat(), "end": bstart.isoformat()})
        cursor = max(cursor, bend)
    if cursor < end and (end - cursor) >= timedelta(minutes=min_minutes):
        slots.append({"start": cursor.isoformat(), "end": end.isoformat()})
    return slots
