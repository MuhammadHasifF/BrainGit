"""Fallback agent for the General topic.

No tools — just chat. Useful as a safety net for messages that land
outside a specialised topic.
"""

from __future__ import annotations

from brainbot.agents.base import BaseAgent


class GeneralAgent(BaseAgent):
    name = "general"
    system_prompt = (
        "You are brainbot, a concise personal assistant. The user is talking to you "
        "in the General topic of their personal Telegram group. Be direct, use "
        "Markdown sparingly, and suggest moving to a more specific topic (Emails, "
        "Calendar, Todos, Second Brain) when relevant."
    )

    def register_tools(self) -> None:
        pass  # no tools; pure chat
