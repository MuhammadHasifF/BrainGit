"""Gemini wrapper.

Thin async layer over `google-genai` that:
- Exposes a single `generate(...)` call that drives a function-calling
  loop (model asks for tool -> we run it -> we feed result back -> loop).
- Returns the final text reply once the model stops calling tools.
- Handles a configurable model (fast or smart) per call.

DESIGN NOTE: `google-genai` is synchronous-by-default but exposes
coroutine-friendly methods on its `AsyncClient`. We run blocking SDK
calls in a thread when needed.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types as gtypes

from brainbot.config import get_settings
from brainbot.llm.tools import ToolRegistry
from brainbot.utils.logging import get_logger

log = get_logger(__name__)


# Bound the function-calling loop so a runaway model can't burn the free tier.
MAX_TOOL_TURNS = 8


@dataclass(slots=True)
class GenerationResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class GeminiClient:
    def __init__(self) -> None:
        settings = get_settings()
        # `genai.Client` is thread-safe; we share one instance.
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._fast_model = settings.gemini_model_fast
        self._smart_model = settings.gemini_model_smart
        self._embed_model = settings.gemini_embedding_model

    # ── Generation with function calling ──────────────────────────────

    async def generate(
        self,
        *,
        prompt: str,
        system_instruction: str | None = None,
        tools: ToolRegistry | None = None,
        smart: bool = False,
        history: list[gtypes.Content] | None = None,
    ) -> GenerationResult:
        """Run a function-calling loop and return the final text reply."""
        model = self._smart_model if smart else self._fast_model

        config_kwargs: dict[str, Any] = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if tools is not None and tools.all():
            config_kwargs["tools"] = [
                gtypes.Tool(function_declarations=tools.to_gemini_declarations())
            ]
            # Let the model decide whether to call tools.
            config_kwargs["tool_config"] = gtypes.ToolConfig(
                function_calling_config=gtypes.FunctionCallingConfig(mode="AUTO")
            )

        config = gtypes.GenerateContentConfig(**config_kwargs)

        contents: list[gtypes.Content] = list(history or [])
        contents.append(
            gtypes.Content(role="user", parts=[gtypes.Part.from_text(prompt)])
        )

        executed_calls: list[dict[str, Any]] = []

        for turn in range(MAX_TOOL_TURNS):
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=model,
                contents=contents,
                config=config,
            )

            function_calls = _extract_function_calls(response)
            if not function_calls:
                return GenerationResult(text=response.text or "", tool_calls=executed_calls)

            # Append the model's tool-call turn to history.
            contents.append(response.candidates[0].content)

            # Execute every requested tool and append their results.
            tool_response_parts: list[gtypes.Part] = []
            for call in function_calls:
                tool = tools.get(call["name"]) if tools else None
                if tool is None:
                    result: Any = {"error": f"unknown tool {call['name']}"}
                else:
                    try:
                        result = await tool.handler(dict(call["args"] or {}))
                    except Exception as exc:  # noqa: BLE001
                        log.exception("tool_handler_failed", tool=call["name"])
                        result = {"error": str(exc)}

                executed_calls.append({"name": call["name"], "args": call["args"], "result": result})
                tool_response_parts.append(
                    gtypes.Part.from_function_response(
                        name=call["name"],
                        response={"result": _json_safe(result)},
                    )
                )

            contents.append(gtypes.Content(role="tool", parts=tool_response_parts))
            log.info("tool_loop_turn", turn=turn, calls=[c["name"] for c in function_calls])

        log.warning("max_tool_turns_reached")
        return GenerationResult(text="(stopped: too many tool calls)", tool_calls=executed_calls)

    # ── Embeddings ────────────────────────────────────────────────────

    async def embed(self, text: str) -> list[float]:
        """Single-string embedding via text-embedding-004."""
        response = await asyncio.to_thread(
            self._client.models.embed_content,
            model=self._embed_model,
            contents=text,
        )
        return list(response.embeddings[0].values)


# ── Helpers ────────────────────────────────────────────────────────────

def _extract_function_calls(response: Any) -> list[dict[str, Any]]:
    """Pull function-call Parts out of a Gemini response."""
    calls: list[dict[str, Any]] = []
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", []) or []:
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None):
                calls.append({"name": fc.name, "args": dict(fc.args or {})})
    return calls


def _json_safe(value: Any) -> Any:
    """Round-trip via JSON to drop non-serialisable types (datetimes, etc)."""
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


# Module-level singleton for convenience.
_client: GeminiClient | None = None


def get_llm() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
