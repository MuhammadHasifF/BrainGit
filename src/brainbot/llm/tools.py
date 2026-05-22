"""Tool (function) definitions used with Gemini function calling.

Each Tool is a (name, description, JSON-schema parameters, async handler)
tuple. Agents register the subset they want exposed to the model. The
LLM client converts these into the Gemini `Tool` SDK type and dispatches
calls back to the handler.

The handler is an `async (args: dict) -> Any` that returns a JSON-
serialisable result (string, dict, list). Whatever it returns is fed
back to the model as the function response.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    handler: ToolHandler


class ToolRegistry:
    """Holds a set of tools and resolves them by name."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.add(t)

    def add(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def to_gemini_declarations(self) -> list[dict[str, Any]]:
        """Render as Gemini `FunctionDeclaration` dicts."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]


# ── Common parameter shapes reused across agents ────────────────────────

def schema_object(props: dict[str, dict[str, Any]], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required or [],
    }


def schema_string(description: str, enum: list[str] | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"type": "string", "description": description}
    if enum:
        d["enum"] = enum
    return d


def schema_integer(description: str) -> dict[str, Any]:
    return {"type": "integer", "description": description}


def schema_array(items: dict[str, Any], description: str) -> dict[str, Any]:
    return {"type": "array", "items": items, "description": description}
