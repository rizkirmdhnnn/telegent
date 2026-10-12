"""Integration test CallSession memakai fake (tanpa jaringan/native)."""

from __future__ import annotations

import asyncio
import time

import numpy as np
from helpers import FakeLiveSession, FakeSink, make_session

from telegent.ai.events import AudioOut, ToolCallEvent, TranscriptIn, TurnComplete
from telegent.ai.tools.registry import ToolRegistry
from telegent.ai.tools.spec import ToolSpec
from telegent.telegram.call_session import SessionState


async def _wait(predicate, timeout: float = 2.0) -> bool:
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


async def _cancel(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_receiver_memproses_beberapa_giliran(settings):
    # 600 sampel 24 kHz -> 1200 sampel 48 kHz = 2400 byte/giliran; 2 giliran = 5 frame.
    pcm = np.arange(600, dtype=np.int16).tobytes()
    live = FakeLiveSession([AudioOut(pcm), TurnComplete(), AudioOut(pcm), TurnComplete()])
    session = make_session(settings=settings, live=live)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False

    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        ok = await _wait(lambda: session.tg_out_queue.qsize() >= 5)
    finally:
        await _cancel(task)

    assert ok
    assert session.tg_out_queue.qsize() == 5


async def test_tool_call_dieksekusi_dan_direspons(settings):
    received = []

    async def handler(ctx, args):
        received.append((ctx.user_id, args))
        return {"pong": True}

    registry = ToolRegistry().register(ToolSpec(name="ping", description="d", handler=handler))
    live = FakeLiveSession([ToolCallEvent(id="abc", name="ping", args={"n": 1})])
    session = make_session(settings=settings, live=live, tools=registry)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False

    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        ok = await _wait(lambda: len(live.tool_responses) >= 1)
    finally:
        await _cancel(task)

    assert ok
    assert received == [(1, {"n": 1})]
    assert live.tool_responses[0].response == {"output": {"pong": True}}


def test_barge_in_mengosongkan_antrean(settings):
    session = make_session(settings=settings, live=FakeLiveSession())
    for _ in range(10):
        session.tg_out_queue.put_nowait(b"\x01" * settings.tg_frame_bytes)
    session.flush_outbound()
    assert session.tg_out_queue.empty()


def test_finish_greeting_bersihkan_buffer(settings):
    session = make_session(settings=settings, live=FakeLiveSession())
    session.gemini_in_queue.put_nowait(b"x")
    session.finish_greeting()
    assert session.is_greeting is False
    assert session.gemini_in_queue.empty()


async def test_sender_mengirim_ke_sink(settings):
    sink = FakeSink()
    live = FakeLiveSession()
    session = make_session(settings=settings, live=live, sink=sink)
    session.state = SessionState.ACTIVE

    task = asyncio.create_task(session._telegram_audio_sender_worker())
    try:
        ok = await _wait(lambda: len(sink.frames) >= 5)
    finally:
        await _cancel(task)

    assert ok, "sender harus mengirim frame (senyap saat antrean kosong)"


async def test_schedule_hangup_setelah_audio_habis(settings):
    live = FakeLiveSession()
    session = make_session(settings=settings, live=live)
    session._live = live

    fired = asyncio.Event()

    async def on_hangup() -> None:
        fired.set()

    session.on_hangup = on_hangup

    # Simulasi audio pamitan AI masih diputar.
    for _ in range(3):
        session.tg_out_queue.put_nowait(b"\x01" * settings.tg_frame_bytes)

    session.schedule_hangup()
    await asyncio.sleep(0.1)
    assert not fired.is_set(), "jangan hangup selama audio masih ada"

    while not session.tg_out_queue.empty():
        session.tg_out_queue.get_nowait()

    await asyncio.wait_for(fired.wait(), timeout=3.0)
    assert fired.is_set()


async def test_schedule_hangup_idempoten(settings):
    session = make_session(settings=settings, live=FakeLiveSession())

    async def noop() -> None: ...

    session.on_hangup = noop
    session.schedule_hangup()
    first = session._hangup_task
    session.schedule_hangup()
    assert session._hangup_task is first

    await session.close()


async def test_idle_watchdog_mengirim_konfirmasi(settings):
    settings.idle_enabled = True
    settings.idle_prompt_seconds = 0.2
    settings.idle_hangup_seconds = 100.0

    live = FakeLiveSession()
    session = make_session(settings=settings, live=live)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    session._last_caller_activity = time.monotonic()
    session._last_output_activity = time.monotonic() - 100.0  # AI sudah lama diam

    task = asyncio.create_task(session._idle_watchdog())
    try:
        ok = await _wait(lambda: len(live.prompts) >= 1, timeout=3.0)
    finally:
        await _cancel(task)

    assert ok, "harus mengirim konfirmasi setelah penelpon diam"
    assert live.prompts[0] == settings.idle_prompt_instruction


async def test_idle_watchdog_mengakhiri_bila_tanpa_respons(settings):
    settings.idle_enabled = True
    settings.idle_prompt_seconds = 0.1
    settings.idle_hangup_seconds = 0.2

    live = FakeLiveSession()
    session = make_session(settings=settings, live=live)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    session._last_caller_activity = time.monotonic()
    session._last_output_activity = time.monotonic() - 100.0

    hangup_calls: list[dict] = []
    session.schedule_hangup = lambda *a, **k: hangup_calls.append(k)  # type: ignore[assignment]

    task = asyncio.create_task(session._idle_watchdog())
    try:
        ok = await _wait(lambda: len(hangup_calls) >= 1, timeout=4.0)
    finally:
        await _cancel(task)

    assert ok, "harus mengakhiri panggilan bila tetap tidak ada respons"
    # Konfirmasi lalu pamitan terkirim sebelum menutup.
    assert len(live.prompts) >= 2
    assert hangup_calls[0].get("min_wait", 0) > 0


def test_note_caller_activity_mereset_status(settings):
    session = make_session(settings=settings, live=FakeLiveSession())
    session._idle_prompted = True
    session._note_caller_activity()
    assert session._idle_prompted is False


async def test_transcript_penelpon_mereset_idle(settings):
    live = FakeLiveSession([TranscriptIn("halo, masih ada")])
    session = make_session(settings=settings, live=live)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    session._last_caller_activity = 0.0

    task = asyncio.create_task(session._gemini_receiver_worker())
    try:
        ok = await _wait(lambda: session._last_caller_activity > 0.0)
    finally:
        await _cancel(task)

    assert ok, "ucapan penelpon harus mereset timer diam"


async def test_batas_durasi_panggilan_memicu_hangup(settings):
    settings.max_call_duration = 0.1
    session = make_session(settings=settings, live=FakeLiveSession())
    session.state = SessionState.ACTIVE

    fired = asyncio.Event()

    async def on_hangup() -> None:
        fired.set()

    session.on_hangup = on_hangup

    await asyncio.wait_for(session._enforce_max_duration(), timeout=2.0)
    await asyncio.wait_for(fired.wait(), timeout=3.0)
    assert fired.is_set()

    await session.close()


async def test_batas_durasi_nol_tidak_memicu_hangup(settings):
    settings.max_call_duration = 0
    session = make_session(settings=settings, live=FakeLiveSession())
    session.state = SessionState.ACTIVE

    # Tanpa batas: task langsung selesai tanpa menjadwalkan hangup.
    await asyncio.wait_for(session._enforce_max_duration(), timeout=1.0)
    assert session._hangup_task is None


# ------------------- regresi: jendela idle dihitung sejak AI selesai bicara


async def test_prompt_tidak_menyala_langsung_setelah_ai_selesai_bicara(settings):
    """Regresi (2026-10-11): jendela idle harus dihitung sejak AI berhenti bicara.

    Sebelumnya dihitung sejak `_last_caller_activity`. Kalau AI menjawab lebih
    lama dari `idle_prompt_seconds`, begitu AI berhenti bicara prompt langsung
    menyala dan penelpon tidak sempat menjawab.
    """
    settings.idle_enabled = True
    settings.idle_prompt_seconds = 3.0
    settings.idle_hangup_seconds = 100.0

    live = FakeLiveSession()
    session = make_session(settings=settings, live=live)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    # Penelpon bicara 60 detik lalu; AI baru saja selesai bicara.
    now = time.monotonic()
    session._last_caller_activity = now - 60.0
    session._last_output_activity = now

    task = asyncio.create_task(session._idle_watchdog())
    try:
        # Timeout harus DI ANTARA IDLE_AI_QUIET_SEC (1.5 dtk) dan
        # idle_prompt_seconds (3 dtk): cukup lama untuk logika lama salah
        # mulai memicu, tapi belum cukup untuk memicu yang benar.
        terlewat = await _wait(lambda: len(live.prompts) >= 1, timeout=2.5)
        assert not terlewat, "prompt menyala sebelum penelpon sempat menjawab"
    finally:
        await _cancel(task)

    assert live.prompts == []


async def test_prompt_menyala_setelah_jendela_since_ai_selesai(settings):
    """Setelah jendela berlalu dari AI selesai bicara, prompt tetap dikirim."""
    settings.idle_enabled = True
    settings.idle_prompt_seconds = 0.2
    settings.idle_hangup_seconds = 100.0

    live = FakeLiveSession()
    session = make_session(settings=settings, live=live)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    now = time.monotonic()
    session._last_caller_activity = now - 60.0
    session._last_output_activity = now

    task = asyncio.create_task(session._idle_watchdog())
    try:
        ok = await _wait(lambda: len(live.prompts) >= 1, timeout=4.0)
    finally:
        await _cancel(task)

    assert ok
    assert live.prompts[0] == settings.idle_prompt_instruction


async def test_jendela_diambil_dari_peristiwa_terakhir(settings):
    """Bila penelpon bicara SETELAH AI, jendela dihitung dari pembicaraan penelpon."""
    settings.idle_enabled = True
    settings.idle_prompt_seconds = 0.2
    settings.idle_hangup_seconds = 100.0

    live = FakeLiveSession()
    session = make_session(settings=settings, live=live)
    session._live = live
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    now = time.monotonic()
    # AI bicara 60 detik lalu; penelpon baru bicara sekarang.
    session._last_output_activity = now - 60.0
    session._last_caller_activity = now

    task = asyncio.create_task(session._idle_watchdog())
    try:
        ok = await _wait(lambda: len(live.prompts) >= 1, timeout=4.0)
    finally:
        await _cancel(task)

    assert ok, "jendela harus dihitung dari pembicaraan penelpon terakhir"
