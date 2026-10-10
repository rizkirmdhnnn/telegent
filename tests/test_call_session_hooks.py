"""Test callback `on_event` pada `CallSession` (bagian E1 di inti).

Callback bersifat opsional (default `None`) sehingga sesi lama — termasuk yang
dipakai pengujian di file lain — tidak berubah perilakunya.
"""

from __future__ import annotations

import asyncio

from helpers import FakeLiveSession, make_session

from telegent.ai.events import ToolCallEvent, TranscriptIn, TranscriptOut
from telegent.ai.tools.registry import ToolRegistry
from telegent.ai.tools.spec import ToolSpec
from telegent.telegram.call_session import END_REASON_IDLE, SessionState


async def _kumpulkan(session, live_events, *, timeout: float = 2.0) -> list[tuple[str, dict]]:
    """Jalankan receiver worker sampai seluruh event selesai diproses."""
    events: list[tuple[str, dict]] = []
    live = FakeLiveSession(live_events)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        for _ in range(int(timeout / 0.01)):
            if not live._events:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return events


def test_hook_opsional_default_none(settings) -> None:
    """Sesi tanpa pemantau tidak menambah apa pun pada jalur pemrosesan."""
    session = make_session(settings=settings, live=FakeLiveSession())
    assert session._on_event is None
    session._notify("transcript", {"text": "halo"})  # tidak boleh melempar


async def test_transkrip_penelpon_dan_ai_dilaporkan(settings) -> None:
    events: list[tuple[str, dict]] = []
    live = FakeLiveSession([TranscriptIn("halo"), TranscriptOut("hai, saya bot")])
    session = make_session(settings=settings, live=live, on_event=lambda e, d: events.append((e, d)))
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False

    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        for _ in range(200):
            if len(events) >= 2:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert [(e, d["speaker"], d["text"]) for e, d in events] == [
        ("transcript", "caller", "halo"),
        ("transcript", "ai", "hai, saya bot"),
    ]


async def test_tool_call_dilaporkan_dengan_status_dan_durasi(settings) -> None:
    events: list[tuple[str, dict]] = []

    async def handler(_ctx, _args):
        return {"ok": True}

    registry = ToolRegistry().register(
        ToolSpec(name="get_current_datetime", description="d", handler=handler)
    )
    live = FakeLiveSession([ToolCallEvent(id="t1", name="get_current_datetime", args={"tz": " WIB"})])
    session = make_session(
        settings=settings, live=live, tools=registry, on_event=lambda e, d: events.append((e, d))
    )
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False

    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        for _ in range(300):
            if any(e == "tool_call" for e, _ in events):
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    tool_events = [d for e, d in events if e == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0]["name"] == "get_current_datetime"
    assert tool_events[0]["args"] == {"tz": " WIB"}
    assert tool_events[0]["status"] == "ok"
    assert tool_events[0]["result"] == {"output": {"ok": True}}
    assert tool_events[0]["duration_ms"] >= 0


async def test_tool_gagal_ditandai_error(settings) -> None:
    events: list[tuple[str, dict]] = []

    async def handler(_ctx, _args):
        raise RuntimeError("ledakan")

    registry = ToolRegistry().register(
        ToolSpec(name="end_call", description="d", handler=handler)
    )
    live = FakeLiveSession([ToolCallEvent(id="t1", name="end_call", args={})])
    session = make_session(
        settings=settings, live=live, tools=registry, on_event=lambda e, d: events.append((e, d))
    )
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False

    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        for _ in range(300):
            if any(e == "tool_call" for e, _ in events):
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    tool_events = [d for e, d in events if e == "tool_call"]
    assert tool_events[0]["status"] == "error"
    assert "ledakan" in tool_events[0]["result"]["error"]


async def test_hook_yang_lempar_tidak_mengganggu_sesi(settings) -> None:
    """Pemantau yang rusak tidak boleh menjatuhkan pemrosesan audio."""

    def bocah(_event, _data):
        raise RuntimeError("monitor mati")

    live = FakeLiveSession([TranscriptIn("halo")])
    session = make_session(settings=settings, live=live, on_event=bocah)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False

    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        for _ in range(200):
            if session._last_caller_activity > 0.0:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert session._last_caller_activity > 0.0
    assert not task.done() or task.cancelled() or task.exception() is None


async def test_schedule_hangup_mencatat_alasan(settings) -> None:
    session = make_session(settings=settings, live=FakeLiveSession())
    session.schedule_hangup(reason=END_REASON_IDLE)
    assert session.end_reason == END_REASON_IDLE

    await session.close()


async def test_alasan_hangup_default_ai(settings) -> None:
    session = make_session(settings=settings, live=FakeLiveSession())
    session.schedule_hangup()
    assert session.end_reason == "ai_end_call"

    await session.close()