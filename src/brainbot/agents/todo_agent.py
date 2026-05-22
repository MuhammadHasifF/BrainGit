"""Todo agent — CRUD over the `todos` table.

Reminders write rows into `scheduled_reminders`; the scheduler picks
those up and fires Telegram messages at fire_at.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from dateutil import parser as dateparser
from sqlalchemy import select

from brainbot.agents.base import BaseAgent
from brainbot.db import session_scope
from brainbot.llm.tools import Tool, schema_object, schema_string
from brainbot.models import ScheduledReminder, Todo
from brainbot.utils.time import local_tz, now_local, now_utc, to_utc


class TodoAgent(BaseAgent):
    name = "todo"
    smart = False
    system_prompt = (
        "You are the Todo agent. Help the user manage a personal todo list.\n"
        "Always pick the simplest tool for the job. When the user says 'add ...', "
        "use add_todo. When they say 'done X' or 'mark X complete', use "
        "complete_todo. For listing, prefer status='open' unless they ask "
        "otherwise. Be terse — one line per todo when listing."
    )

    def register_tools(self) -> None:
        self.tools.add(Tool(
            name="add_todo",
            description="Add a new todo. Supports optional due/reminder times and tags.",
            parameters=schema_object(
                {
                    "content": schema_string("Free-text description."),
                    "due_at": schema_string("Optional due time (ISO or natural language)."),
                    "reminder_at": schema_string("Optional reminder time."),
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags.",
                    },
                    "recurring_rule": schema_string(
                        "Optional RRULE string, e.g. 'FREQ=DAILY;BYHOUR=9'."
                    ),
                },
                required=["content"],
            ),
            handler=_add_todo,
        ))

        self.tools.add(Tool(
            name="list_todos",
            description="List todos by status or tag.",
            parameters=schema_object(
                {
                    "status": schema_string(
                        "'open', 'completed', or 'all'.",
                        enum=["open", "completed", "all"],
                    ),
                    "tag": schema_string("Optional tag filter."),
                    "due_before": schema_string("Optional: only todos due before this time."),
                },
            ),
            handler=_list_todos,
        ))

        self.tools.add(Tool(
            name="complete_todo",
            description="Mark a todo complete by id.",
            parameters=schema_object(
                {"todo_id": {"type": "integer", "description": "Todo id."}},
                required=["todo_id"],
            ),
            handler=_complete_todo,
        ))

        self.tools.add(Tool(
            name="delete_todo",
            description="Permanently delete a todo by id.",
            parameters=schema_object(
                {"todo_id": {"type": "integer", "description": "Todo id."}},
                required=["todo_id"],
            ),
            handler=_delete_todo,
        ))


# ── Helpers ────────────────────────────────────────────────────────────

def _parse(when: str | None) -> datetime | None:
    if not when:
        return None
    return dateparser.parse(when, default=now_local(), fuzzy=True).replace(tzinfo=local_tz())


def _serialise(t: Todo) -> dict[str, Any]:
    return {
        "id": t.id,
        "content": t.content,
        "status": t.status,
        "tags": t.tags,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "reminder_at": t.reminder_at.isoformat() if t.reminder_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


# ── Tool handlers ──────────────────────────────────────────────────────

async def _add_todo(args: dict[str, Any]) -> dict[str, Any]:
    due = _parse(args.get("due_at"))
    reminder = _parse(args.get("reminder_at"))
    async with session_scope() as session:
        todo = Todo(
            content=args["content"],
            status="open",
            due_at=to_utc(due) if due else None,
            reminder_at=to_utc(reminder) if reminder else None,
            tags=list(args.get("tags") or []),
            recurring_rule=args.get("recurring_rule"),
        )
        session.add(todo)
        await session.flush()  # populate todo.id

        if reminder:
            session.add(ScheduledReminder(todo_id=todo.id, fire_at=to_utc(reminder)))

        return _serialise(todo)


async def _list_todos(args: dict[str, Any]) -> list[dict[str, Any]]:
    status = args.get("status", "open")
    tag = args.get("tag")
    due_before = _parse(args.get("due_before"))

    async with session_scope() as session:
        stmt = select(Todo)
        if status != "all":
            stmt = stmt.where(Todo.status == status)
        if tag:
            stmt = stmt.where(Todo.tags.contains([tag]))
        if due_before:
            stmt = stmt.where(Todo.due_at <= to_utc(due_before))
        stmt = stmt.order_by(Todo.due_at.is_(None), Todo.due_at, Todo.id)
        result = await session.execute(stmt)
        return [_serialise(t) for t in result.scalars()]


async def _complete_todo(args: dict[str, Any]) -> dict[str, Any]:
    async with session_scope() as session:
        todo = await session.get(Todo, int(args["todo_id"]))
        if todo is None:
            return {"error": "not_found"}
        todo.status = "completed"
        todo.completed_at = now_utc()

        # Reschedule if recurring.
        if todo.recurring_rule:
            next_run = _next_recurrence(todo, now_utc())
            if next_run:
                session.add(Todo(
                    content=todo.content,
                    status="open",
                    due_at=next_run,
                    reminder_at=next_run - timedelta(minutes=15),
                    tags=todo.tags,
                    recurring_rule=todo.recurring_rule,
                ))
        return _serialise(todo)


async def _delete_todo(args: dict[str, Any]) -> dict[str, str]:
    async with session_scope() as session:
        todo = await session.get(Todo, int(args["todo_id"]))
        if todo is None:
            return {"status": "not_found"}
        await session.delete(todo)
        return {"status": "deleted"}


def _next_recurrence(todo: Todo, after: datetime) -> datetime | None:
    """Compute the next fire time for a recurring todo.

    DESIGN NOTE: minimal RRULE support — only FREQ=DAILY|WEEKLY for now.
    Full RRULE handling can come later if I actually use recurring todos.
    """
    rule = (todo.recurring_rule or "").upper()
    if "FREQ=DAILY" in rule:
        return after + timedelta(days=1)
    if "FREQ=WEEKLY" in rule:
        return after + timedelta(days=7)
    return None
