"""Test hook persistensi panggilan (tiket E1).

Yang diuji di sini:

* `call_record` dibuat saat panggilan **masuk**, termasuk yang **ditolak**
  (Q12), dengan `outcome` yang benar.
* Transkrip & tool call tersimpan dan terhubung ke record induknya.
* Event live terkirim ke `EventBus` (dipantau lewat subscriber).
* **Pipeline audio tidak melambat** — hook hanya mengantrekan pekerjaan.
* `store_transcripts=false` benar-benar menghentikan penyimpanan teks.
* Secret disamarkan pada transkrip maupun argumen/hasil tool.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from telegent.web import call_store
from telegent.web.call_recorder import CallRecorder, build_recorder
from telegent.web.db.base import Database, utcnow
from telegent.web.events import EventBus, Event
from telegent.web.log_stream import SecretRedactor

SECRET_KEY = "AIzaSy0123456789012345678901234567890"


# ------------------------------------------------------------------ fixture


@pytest.fixture
async def recorder(database: Database) -> CallRecorder:
    """Perekam aktif dengan bus, siap dipakai lalu ditutup bersih."""
    rec = CallRecorder(database, bus=EventBus(), redactor=SecretRedactor([SECRET_KEY]))
    rec.start()
    try:
        yield rec
    finally:
        await rec.aclose()


async def _record_call(rec: CallRecorder) -> int:
    """Jalankan satu siklus panggilan penuh; kembalikan `call_record.id`."""
    rec.call_incoming(9, 123, user_display="@budi")
    rec.call_started(9, 123)
    await rec.flush()
    assert rec.record_id_for(9) is not None
    return rec.record_id_for(9)  # type: ignore[return-value]


def _events(bus: EventBus, kind: str) -> list[Event]:
    return [event for event in bus.history() if event.type == kind]


# -------------------------------------------------------------- call record


async def test_panggilan_masuk_membuat_call_record(recorder: CallRecorder) -> None:
    record_id = await _record_call(recorder)

    detail = await call_store.get_call(recorder.db, record_id)
    assert detail is not None
    assert detail.tg_call_id == 9
    assert detail.user_id == 123
    assert detail.user_display == "@budi"
    assert detail.outcome == call_store.OUTCOME_PENDING
    assert detail.ended_at is None


async def test_panggilan_selesai_mencatat_durasi_dan_outcome(
    recorder: CallRecorder,
) -> None:
    record_id = await _record_call(recorder)
    recorder.call_ended(9, 123, outcome="answered", end_reason="caller_hangup", duration_sec=42)
    await recorder.flush()

    detail = await call_store.get_call(recorder.db, record_id)
    assert detail is not None
    assert detail.outcome == "answered"
    assert detail.end_reason == "caller_hangup"
    assert detail.duration_sec == 42
    assert detail.ended_at is not None


@pytest.mark.parametrize(
    "outcome",
    [
        call_store.OUTCOME_REJECTED_WHITELIST,
        call_store.OUTCOME_REJECTED_RATELIMIT,
        call_store.OUTCOME_REJECTED_CAPACITY,
        call_store.OUTCOME_REJECTED_DUPLICATE,
        call_store.OUTCOME_ERROR,
    ],
)
async def test_setiap_outcome_penolakan_tercatat(
    recorder: CallRecorder, outcome: str
) -> None:
    """Q12: panggilan yang ditolak tetap menghasilkan satu `call_record`."""
    recorder.call_incoming(9, 123)
    recorder.call_ended(9, 123, outcome=outcome, end_reason="rejected")
    await recorder.flush()

    page = await call_store.list_calls(recorder.db, call_store.CallFilters())
    assert page.total == 1
    assert page.items[0].outcome == outcome
    assert page.items[0].end_reason == "rejected"
    assert page.items[0].duration_sec == 0


# ---------------------------------------------------------------- transkrip


async def test_transkrip_tersimpan_terurut_waktu(recorder: CallRecorder) -> None:
    record_id = await _record_call(recorder)
    for speaker, text in (("caller", "halo"), ("ai", "halo, ada yang bisa dibantu?")):
        recorder.session_event(9, "transcript", {"speaker": speaker, "text": text})
    await recorder.flush()

    rows = await call_store.list_transcripts(recorder.db, record_id)
    assert [(row.speaker, row.text) for row in rows] == [
        ("caller", "halo"),
        ("ai", "halo, ada yang bisa dibantu?"),
    ]

    detail = await call_store.get_call(recorder.db, record_id)
    assert detail is not None and detail.transcript_count == 2


async def test_transkrip_kosong_tidak_disimpan(recorder: CallRecorder) -> None:
    record_id = await _record_call(recorder)
    recorder.session_event(9, "transcript", {"speaker": "caller", "text": "   "})
    await recorder.flush()

    assert await call_store.list_transcripts(recorder.db, record_id) == []


async def test_store_transcripts_mati_tidak_menyimpan_teks(
    recorder: CallRecorder,
) -> None:
    """Q13: `store_transcripts=false` mematikan penyimpanan maupun penyiaran."""
    record_id = await _record_call(recorder)
    recorder.set_store_transcripts(False)
    assert recorder.store_transcripts is False

    recorder.session_event(9, "transcript", {"speaker": "caller", "text": "rahasia"})
    recorder.session_event(
        9, "transcript", {"speaker": "ai", "text": f"kunci saya {SECRET_KEY}"}
    )
    await recorder.flush()

    assert await call_store.list_transcripts(recorder.db, record_id) == []
    assert _events(recorder.bus, "transcript") == []

    # Tool call tetap disimpan: bukan rekaman suara, hanya metadata.
    recorder.session_event(9, "tool_call", {"name": "get_current_datetime", "args": {}})
    await recorder.flush()
    assert len(await call_store.list_tool_calls(recorder.db, record_id)) == 1


# --------------------------------------------------------------- tool call


async def test_tool_call_tersimpan_lengkap(recorder: CallRecorder) -> None:
    record_id = await _record_call(recorder)
    recorder.session_event(
        9,
        "tool_call",
        {
            "name": "get_current_datetime",
            "args": {"timezone": "Asia/Jakarta"},
            "result": {"output": {"iso": "2026-01-01T00:00:00+07:00"}},
            "status": "ok",
            "duration_ms": 12,
        },
    )
    await recorder.flush()

    rows = await call_store.list_tool_calls(recorder.db, record_id)
    assert len(rows) == 1
    assert rows[0].name == "get_current_datetime"
    assert rows[0].status == "ok"
    assert rows[0].duration_ms == 12
    assert "Asia/Jakarta" in (rows[0].args_json or "")
    assert "iso" in (rows[0].result_json or "")

    detail = await call_store.get_call(recorder.db, record_id)
    assert detail is not None and detail.tool_call_count == 1


@pytest.mark.parametrize(
    ("status", "durasi"),
    [("error", 5), ("timeout", 2000), ("cancelled", 0)],
)
async def test_status_tool_bersifat_lengkap(
    recorder: CallRecorder, status: str, durasi: int
) -> None:
    record_id = await _record_call(recorder)
    recorder.session_event(
        9, "tool_call", {"name": "end_call", "status": status, "duration_ms": durasi}
    )
    await recorder.flush()

    rows = await call_store.list_tool_calls(recorder.db, record_id)
    assert rows[0].status == status
    assert rows[0].duration_ms == durasi


# ------------------------------------------------------------------ redaksi


async def test_secret_disamarkan_pada_transkrip_dan_tool(recorder: CallRecorder) -> None:
    record_id = await _record_call(recorder)
    recorder.session_event(
        9, "transcript", {"speaker": "caller", "text": f"api key {SECRET_KEY} saya"}
    )
    recorder.session_event(
        9,
        "tool_call",
        {"name": "end_call", "args": {"key": SECRET_KEY}, "status": "ok"},
    )
    await recorder.flush()

    transcripts = await call_store.list_transcripts(recorder.db, record_id)
    assert SECRET_KEY not in transcripts[0].text
    assert "[REDACTED]" in transcripts[0].text

    tools = await call_store.list_tool_calls(recorder.db, record_id)
    assert SECRET_KEY not in (tools[0].args_json or "")

    for event in _events(recorder.bus, "transcript"):
        assert SECRET_KEY not in event.data["text"]


# -------------------------------------------------------------- event live


async def test_event_siklus_hidup_terbit_ke_bus(recorder: CallRecorder) -> None:
    recorder.call_incoming(9, 123)
    recorder.call_started(9, 123)
    recorder.session_event(9, "transcript", {"speaker": "ai", "text": "halo"})
    recorder.session_event(9, "tool_call", {"name": "end_call", "status": "ok"})
    recorder.call_ended(9, 123, outcome="answered", end_reason="ai_end_call", duration_sec=7)

    bus: EventBus = recorder.bus
    assert bus is not None
    assert [event.type for event in bus.history()] == [
        "call.incoming",
        "call.started",
        "transcript",
        "tool_call",
        "call.ended",
    ]
    ended = bus.history()[-1]
    assert ended.data["outcome"] == "answered"
    assert ended.data["end_reason"] == "ai_end_call"
    assert ended.data["duration_sec"] == 7


async def test_transcript_tail_untuk_panggilan_aktif(recorder: CallRecorder) -> None:
    await _record_call(recorder)
    for index in range(15):
        recorder.session_event(9, "transcript", {"speaker": "ai", "text": f"baris {index}"})

    tail = recorder.transcript_tail(9)
    assert len(tail) == 10
    assert tail[-1]["text"] == "baris 14"


# ------------------------------------------------- jalur audio tidak melambat


async def test_hook_tidak_memblokir_penerimaan_audio(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Db lambat tidak boleh memperlambat jalur audio 10 ms.

    Penulisan ke database sengaja dibuat sangat lambat (menunggu `gate`),
    sementara pemanggilan hook hanya mengantrekan pekerjaan. Hook 400 kali
    harus selesai jauh sebelum penulisan itu dibuka.
    """
    gate = asyncio.Event()

    async def lambat(*_args, **_kwargs):
        await gate.wait()
        return 1

    monkeypatch.setattr(call_store, "start_call", lambat)
    monkeypatch.setattr(call_store, "add_transcript", lambat)
    monkeypatch.setattr(call_store, "add_tool_call", lambat)

    rec = CallRecorder(database, bus=EventBus())
    rec.start()
    try:
        loop = asyncio.get_running_loop()
        mulai = loop.time()
        for index in range(200):
            rec.session_event(9, "transcript", {"speaker": "ai", "text": f"baris {index}"})
            rec.session_event(9, "tool_call", {"name": "end_call", "status": "ok"})
        durasi_hook = loop.time() - mulai
        gate.set()
        await rec.aclose()
    finally:
        gate.set()

    assert durasi_hook < 0.5, "hook persistensi memblokir jalur audio"


async def test_antrean_penuh_membuang_bukan_memblokir(database: Database) -> None:
    """Pengikut lambat: pekerjaan monitoring dibuang, pemanggil tidak menunggu."""
    rec = CallRecorder(database, bus=EventBus(), queue_size=4)
    rec.start()
    try:
        for index in range(100):
            rec.session_event(9, "transcript", {"speaker": "ai", "text": str(index)})
        assert rec.dropped > 0
    finally:
        await rec.aclose()


async def test_antrean_kosong_tetap_menulis_semua(database: Database) -> None:
    rec = CallRecorder(database, bus=EventBus(), queue_size=10_000)
    rec.start()
    try:
        rec.call_incoming(9, 123)
        for index in range(50):
            rec.session_event(9, "transcript", {"speaker": "ai", "text": f"baris {index}"})
        rec.call_ended(9, 123, outcome="answered", end_reason="caller_hangup", duration_sec=10)
        await rec.aclose()
    finally:
        await rec.aclose()

    page = await call_store.list_calls(database, call_store.CallFilters())
    assert page.total == 1
    detail = await call_store.get_call(database, page.items[0].id)
    assert detail is not None and detail.transcript_count == 50
    assert rec.dropped == 0


# ------------------------------------------------------------ gabungan


async def test_build_recorder_membaca_store_transcripts(database, store) -> None:
    rec = await build_recorder(database, store, bus=EventBus())
    try:
        # Default registry adalah `true` (Q13).
        assert rec.store_transcripts is True
    finally:
        await rec.aclose()


async def test_event_tanpa_pemantau_tidak_melempar(database: Database) -> None:
    """Tanpa bus maupun redactor, hook tetap aman (mode headless)."""
    rec = CallRecorder(database)
    rec.call_incoming(1, 2)
    rec.call_started(1, 2)
    rec.session_event(1, "transcript", {"speaker": "ai", "text": "halo"})
    rec.session_event(1, "tool_call", {"name": "end_call", "status": "ok", "duration_ms": 1})
    rec.call_ended(1, 2, outcome="answered", end_reason="ai_end_call", duration_sec=3)
    rec.start()
    await rec.aclose()

    page = await call_store.list_calls(database, call_store.CallFilters())
    assert page.total == 1