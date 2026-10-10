"""Unit test untuk sistem tool calling."""

from __future__ import annotations

import asyncio

import pytest

from telegent.ai.tools.builtin import make_datetime_tool
from telegent.ai.tools.registry import ToolRegistry
from telegent.ai.tools.spec import ToolContext, ToolRequest, ToolSpec


def _ctx() -> ToolContext:
    return ToolContext(user_id=7, call_id=9)


def test_declarations_kosong_bila_tanpa_tool():
    assert ToolRegistry().declarations() is None


def test_declarations_membentuk_tool_gemini():
    async def handler(ctx, args):
        return {"ok": True}

    registry = ToolRegistry().register(
        ToolSpec(
            name="foo",
            description="contoh",
            handler=handler,
            parameters_json_schema={"type": "object", "properties": {"a": {"type": "string"}}},
        )
    )
    declarations = registry.declarations()
    assert declarations is not None
    fn = declarations[0].function_declarations[0]
    assert fn.name == "foo"
    assert fn.description == "contoh"


def test_register_duplikat_error():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="d", description="d", handler=lambda c, a: {}))
    with pytest.raises(ValueError):
        registry.register(ToolSpec(name="d", description="d", handler=lambda c, a: {}))


async def test_execute_sukses():
    calls = []

    async def handler(ctx, args):
        calls.append((ctx.user_id, args))
        return {"echo": args.get("x")}

    registry = ToolRegistry().register(ToolSpec(name="echo", description="d", handler=handler))
    result = await registry.execute(_ctx(), ToolRequest(id="1", name="echo", args={"x": 5}))
    assert result.response == {"output": {"echo": 5}}
    assert calls == [(7, {"x": 5})]


async def test_execute_tool_tidak_dikenal():
    result = await ToolRegistry().execute(_ctx(), ToolRequest(id="1", name="ghost", args={}))
    assert "error" in result.response


async def test_execute_timeout():
    async def slow(ctx, args):
        await asyncio.sleep(10)
        return {}

    registry = ToolRegistry().register(
        ToolSpec(name="slow", description="d", handler=slow, timeout=0.05)
    )
    result = await registry.execute(_ctx(), ToolRequest(id="1", name="slow", args={}))
    assert "timeout" in result.response["error"]


async def test_execute_error_ditangkap():
    async def boom(ctx, args):
        raise RuntimeError("kaboom")

    registry = ToolRegistry().register(ToolSpec(name="boom", description="d", handler=boom))
    result = await registry.execute(_ctx(), ToolRequest(id="1", name="boom", args={}))
    assert result.response == {"error": "kaboom"}


async def test_datetime_tool():
    from telegent.ai.tools.registry import ToolRegistry as Reg

    registry = Reg().register(make_datetime_tool())
    result = await registry.execute(_ctx(), ToolRequest(id="1", name="get_current_datetime", args={}))
    output = result.response["output"]
    assert output["timezone"] == "Asia/Jakarta"
    assert "iso" in output and "human" in output
