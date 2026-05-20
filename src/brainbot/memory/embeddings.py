"""Embedding helpers — thin wrapper over the Gemini client."""

from __future__ import annotations

from brainbot.llm.client import get_llm


async def embed_text(text: str) -> list[float]:
    """Return a 768-dim embedding for `text`."""
    return await get_llm().embed(text)
