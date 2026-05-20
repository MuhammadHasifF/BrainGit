"""Second-brain agent — save + semantic search over notes.

Two modes:
- Quick Notes topic: every message is auto-saved as a note (no tool call,
  no LLM reasoning beyond auto-tagging).
- Second Brain topic: the model decides between save_note,
  semantic_search_notes, and notes_in_range_query.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from dateutil import parser as dateparser

from brainbot.agents.base import BaseAgent
from brainbot.llm.tools import (
    Tool,
    schema_array,
    schema_object,
    schema_string,
)
from brainbot.memory import vector_store
from brainbot.telegram.send import escape_md, send_text
from brainbot.telegram.topics import TopicName
from brainbot.utils.time import local_tz, now_local


class BrainAgent(BaseAgent):
    name = "brain"
    smart = True
    system_prompt = (
        "You are the Second Brain agent. The user dumps notes, reflections, and facts "
        "here. You can save them, search them semantically, or query by date range. "
        "When saving, infer 2-5 short tags. When searching, return the most relevant "
        "5-10 notes with a one-line summary each. Be concise."
    )

    async def handle(self, msg: Any) -> None:  # type: ignore[override]
        # Quick Notes topic = auto-save shortcut.
        if msg.topic == TopicName.QUICK_NOTES and msg.text.strip():
            note = await vector_store.save_note(
                msg.text.strip(), source_topic=msg.topic.value
            )
            await send_text(
                escape_md(f"Saved as note #{note.id}."),
                thread_id=msg.thread_id,
                reply_to_message_id=msg.message_id,
            )
            return
        await super().handle(msg)

    def register_tools(self) -> None:
        self.tools.add(Tool(
            name="save_note",
            description="Save a note to the second brain. Auto-embeds via Gemini.",
            parameters=schema_object(
                {
                    "content": schema_string("Free-text content of the note."),
                    "tags": schema_array(schema_string("Short tag."), "2-5 tags."),
                },
                required=["content"],
            ),
            handler=_save_note,
        ))

        self.tools.add(Tool(
            name="semantic_search_notes",
            description=(
                "Semantic search over saved notes. Optionally constrain to a date range."
            ),
            parameters=schema_object(
                {
                    "query": schema_string("Natural-language search query."),
                    "limit": {"type": "integer", "description": "Default 10."},
                    "since": schema_string("Optional: only notes from this time forward."),
                    "until": schema_string("Optional: only notes up to this time."),
                },
                required=["query"],
            ),
            handler=_semantic_search,
        ))

        self.tools.add(Tool(
            name="notes_in_range_query",
            description="List notes within a date range (chronological, no embedding search).",
            parameters=schema_object(
                {
                    "since": schema_string("Range start."),
                    "until": schema_string("Range end."),
                    "tag": schema_string("Optional tag filter."),
                },
                required=["since", "until"],
            ),
            handler=_in_range,
        ))


# ── Helpers ────────────────────────────────────────────────────────────

def _parse(when: str) -> Any:
    text = when.strip().lower()
    today = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    shortcuts = {
        "today": today,
        "yesterday": today - timedelta(days=1),
        "last week": today - timedelta(days=7),
        "last month": today - timedelta(days=30),
    }
    if text in shortcuts:
        return shortcuts[text]
    return dateparser.parse(when, default=now_local(), fuzzy=True).replace(tzinfo=local_tz())


# ── Tool handlers ──────────────────────────────────────────────────────

async def _save_note(args: dict[str, Any]) -> dict[str, Any]:
    note = await vector_store.save_note(
        content=args["content"], tags=args.get("tags") or [], source_topic="second_brain"
    )
    return vector_store.to_dict(note)


async def _semantic_search(args: dict[str, Any]) -> list[dict[str, Any]]:
    since = _parse(args["since"]) if args.get("since") else None
    until = _parse(args["until"]) if args.get("until") else None
    notes = await vector_store.semantic_search(
        args["query"], limit=int(args.get("limit", 10)), since=since, until=until
    )
    return [vector_store.to_dict(n) for n in notes]


async def _in_range(args: dict[str, Any]) -> list[dict[str, Any]]:
    since = _parse(args["since"])
    until = _parse(args["until"])
    notes = await vector_store.notes_in_range(since=since, until=until, tag=args.get("tag"))
    return [vector_store.to_dict(n) for n in notes]
