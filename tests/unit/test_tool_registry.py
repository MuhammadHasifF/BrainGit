from __future__ import annotations

import pytest

from brainbot.llm.tools import Tool, ToolRegistry, schema_object, schema_string


async def _handler(_args: dict) -> dict:
    return {"ok": True}


def _tool(name: str = "echo") -> Tool:
    return Tool(
        name=name,
        description="returns ok",
        parameters=schema_object({"x": schema_string("anything")}),
        handler=_handler,
    )


def test_registry_add_and_lookup() -> None:
    reg = ToolRegistry()
    reg.add(_tool())
    assert reg.get("echo") is not None
    assert reg.get("missing") is None
    assert reg.names() == ["echo"]


def test_registry_rejects_duplicates() -> None:
    reg = ToolRegistry()
    reg.add(_tool())
    with pytest.raises(ValueError):
        reg.add(_tool())


def test_to_gemini_declarations_shape() -> None:
    reg = ToolRegistry([_tool("a"), _tool("b")])
    decl = reg.to_gemini_declarations()
    assert {d["name"] for d in decl} == {"a", "b"}
    for d in decl:
        assert d["parameters"]["type"] == "object"
