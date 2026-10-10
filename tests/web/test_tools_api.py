"""Pengujian API Tools & ToolRegistry (Tiket C3)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from web_helpers import csrf_of, do_setup

from telegent.ai.tools.builtin import default_tools
from telegent.ai.tools.registry import ToolRegistry
from telegent.ai.tools.spec import ToolContext, ToolRequest


def test_list_tools(live_client: TestClient) -> None:
    do_setup(live_client)
    resp = live_client.get("/api/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert isinstance(tools, list)
    names = {t["name"] for t in tools}
    assert "get_current_datetime" in names
    assert "end_call" in names

    end_call_info = next(t for t in tools if t["name"] == "end_call")
    assert end_call_info["can_disable"] is False
    assert end_call_info["enabled"] is True


def test_cannot_disable_end_call(live_client: TestClient) -> None:
    do_setup(live_client)
    token = csrf_of(live_client)

    resp = live_client.put(
        "/api/tools/end_call",
        json={"enabled": False},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "cannot_disable_tool"


def test_configure_datetime_tool(live_client: TestClient) -> None:
    do_setup(live_client)
    token = csrf_of(live_client)

    resp = live_client.put(
        "/api/tools/get_current_datetime",
        json={
            "enabled": True,
            "config": {"default_timezone": "Asia/Jayapura"},
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Verifikasi saat di-get ulang
    tools_resp = live_client.get("/api/tools")
    assert tools_resp.status_code == 200
    dt_tool = next(t for t in tools_resp.json() if t["name"] == "get_current_datetime")
    assert dt_tool["enabled"] is True
    assert dt_tool["config"] == {"default_timezone": "Asia/Jayapura"}


async def test_tool_registry_toggle_and_declarations() -> None:
    registry = ToolRegistry()
    for spec in default_tools():
        registry.register(spec)

    # Awalnya kedua tool aktif
    decl = registry.declarations()
    assert decl is not None
    funcs = decl[0].function_declarations
    assert funcs is not None
    assert len(funcs) == 2

    # Matikan get_current_datetime
    registry.configure("get_current_datetime", enabled=False)
    decl2 = registry.declarations()
    assert decl2 is not None
    funcs2 = decl2[0].function_declarations
    assert funcs2 is not None
    assert len(funcs2) == 1
    assert funcs2[0].name == "end_call"

    # Eksekusi tool nonaktif
    ctx = ToolContext(user_id=1, call_id=1)
    res = await registry.execute(
        ctx, ToolRequest(id="1", name="get_current_datetime", args={})
    )
    assert "dinonaktifkan" in res.response.get("error", "")
