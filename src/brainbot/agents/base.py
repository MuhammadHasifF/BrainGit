"""Common agent base class.

An agent wraps a `GeminiClient` + a `ToolRegistry`. Subclasses configure
their own system prompt, tools, and (optionally) per-message
pre/post-processing.

Every agent's `handle(msg)` returns nothing — the agent is responsible
for posting its own reply via `brainbot.telegram.send`. This lets the
agent post multiple messages, photos, etc. and avoids forcing a single
text response shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from brainbot.llm.client import GeminiClient, get_llm
from brainbot.llm.tools import ToolRegistry
from brainbot.telegram.send import escape_md, send_text
from brainbot.utils.logging import get_logger

if TYPE_CHECKING:
    from brainbot.telegram.webhook import IncomingMessage


log = get_logger(__name__)


class BaseAgent(ABC):
    name: str = "base"
    system_prompt: str = ""
    smart: bool = False  # if True, use gemini-2.5-pro instead of -flash

    def __init__(self) -> None:
        self.llm: GeminiClient = get_llm()
        self.tools = ToolRegistry()
        self.register_tools()

    @abstractmethod
    def register_tools(self) -> None:
        """Subclasses call self.tools.add(Tool(...)) here."""

    async def handle(self, msg: "IncomingMessage") -> None:
        """Default: run the LLM with our tools and post the result."""
        if not msg.text.strip():
            return
        log.info("agent_handle", agent=self.name, text=msg.text[:80])
        result = await self.llm.generate(
            prompt=msg.text,
            system_instruction=self.system_prompt,
            tools=self.tools,
            smart=self.smart,
        )
        reply = result.text.strip() or "(no response)"
        await send_text(
            escape_md(reply),
            thread_id=msg.thread_id,
            reply_to_message_id=msg.message_id,
        )
