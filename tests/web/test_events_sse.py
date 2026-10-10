"""Test endpoint SSE: replay, event langsung, heartbeat, dan isolateksimu (E2).

Aliran SSE diuji langsung sebagai async generator (bukan lewat `TestClient`,
yang tidak mendukung respons streaming tak berujung).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from web_helpers import do_setup

from telegent.web.db.base import utcnow
from telegent.web.events import Event, EventBus
from telegent.web.log_stream import BusLogHandler, LogRingBuffer
from telegent.web.routers import events as events_router
from telegent.web.routers.events import format_event
from telegent.web.security import AdminSession


def _admin_session() -> AdminSession:
    """Sesi admin palsu; handler hanya butuh dependency terpenuhi."""
    return AdminSession(
        token="token",
        csrf_token="csrf",
        username="admin",
        admin_id=1,
        created_at=utcnow(),
        expires_at=utcnow() + timedelta(hours=1),
    )


# ------------------------------------------------------------------ utilitas


def _record(message: str = "halo"):
    return logging.LogRecord(
        name="telegent.call",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def parse_blocks(raw: str) -> list[dict[str, Any]]:
    """Pecah teks SSE menjadi blok `{id, event, data, comment}`."""
    blocks: list[dict[str, Any]] = []
    for chunk in raw.split("\n\n"):
        if not chunk.strip():
            continue
        block: dict[str, Any] = {"comment": None, "id": None, "event": None, "data": None}
        for line in chunk.splitlines():
            if line.startswith(":"):
                block["comment"] = line[1:].strip()
            elif line.startswith("id: "):
                block["id"] = int(line[4:])
            elif line.startswith("event: "):
                block["event"] = line[7:]
            elif line.startswith("data: "):
                block["data"] = json.loads(line[6:])
            elif line.startswith("retry: "):
                block["retry"] = int(line[7:])
        blocks.append(block)
    return blocks


async def _baca_berikutnya(gen, *, count: int = 1, timeout: float = 2.0) -> list[str]:
    """Baca `count` potongan dari stream dengan batas waktu."""
    hasil: list[str] = []
    for _ in range(count):
        hasil.append(await asyncio.wait_for(gen.__anext__(), timeout=timeout))
    return hasil


# ------------------------------------------------------------------- format


def test_format_event_menghasilkan_blok_sse_lengkap() -> None:
    event = Event(id=7, type="call.ended", data={"outcome": "answered", "user_id": 1})
    raw = format_event(event)

    assert raw.endswith("\n\n")
    assert "id: 7\n" in raw
    assert "event: call.ended\n" in raw
    assert json.loads(raw.split("data: ", 1)[1].strip()) == {
        "outcome": "answered",
        "user_id": 1,
    }


def test_format_event_menangani_data_bukan_dict() -> None:
    """Payload tak serializable tidak boleh menjatuhkan stream."""
    raw = format_event(Event(id=1, type="x", data={"obj": object()}))
    assert raw.startswith("id: 1\n")


# --------------------------------------------------------------- events/stream


async def test_events_stream_mengirim_retry_lalu_event_langsung() -> None:
    bus = EventBus()
    gen = events_router._stream(bus, snapshot=lambda: [])
    try:
        pertama = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert pertama == f"retry: {events_router.SSE_RETRY_MS}\n\n"

        bus.publish("status", {"running": True})
        kedua = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        blocks = parse_blocks(kedua)
        assert blocks[0]["event"] == "status"
        assert blocks[0]["data"] == {"running": True}
    finally:
        await gen.aclose()


async def test_events_stream_mengirim_replay_untuk_klien_baru() -> None:
    bus = EventBus()
    bus.publish("call.ended", {"tg_call_id": 1})
    bus.publish("call.incoming", {"tg_call_id": 2})

    gen = events_router._stream(bus, snapshot=lambda: bus.history(limit=10))
    try:
        potongan = await _baca_berikutnya(gen, count=3)
    finally:
        await gen.aclose()

    blocks = [b for b in parse_blocks("".join(potongan)) if b["event"]]
    assert [b["event"] for b in blocks] == ["call.ended", "call.incoming"]
    assert [b["id"] for b in blocks] == [1, 2]


async def test_events_stream_tidak_mengirim_log() -> None:
    """`/events/stream` khusus status/panggilan; log lewat `/logs/stream`."""
    bus = EventBus()
    gen = events_router._stream(
        bus, snapshot=lambda: bus.history(limit=10), without=frozenset({"log"})
    )
    try:
        await asyncio.wait_for(gen.__anext__(), timeout=1.0)  # retry
        bus.publish("log", {"message": "halo"})
        bus.publish("status", {"running": True})

        blok = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert parse_blocks(blok)[0]["event"] == "status"
    finally:
        await gen.aclose()


async def test_events_mengirim_heartbeat_saat_senyap(monkeypatch) -> None:
    """Tanpa event, server mengirim `: ping` agar proxy tak memutus koneksi."""
    monkeypatch.setattr(events_router, "HEARTBEAT_SEC", 0.05)
    bus = EventBus()

    gen = events_router._stream(bus, snapshot=lambda: [])
    try:
        await asyncio.wait_for(gen.__anext__(), timeout=1.0)  # retry
        blok = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert blok == ": ping\n\n"
    finally:
        await gen.aclose()


# ---------------------------------------------------------------- logs/stream


async def test_logs_stream_mengirim_ring_buffer_lalu_live() -> None:
    bus = EventBus()
    buffer = LogRingBuffer(maxlen=10)
    handler = BusLogHandler(bus, buffer)
    handler.emit(_record("pesan lama"))

    gen = events_router._stream(
        bus, snapshot=lambda: events_router._log_snapshot(buffer), only=frozenset({"log"})
    )
    try:
        potongan = await _baca_berikutnya(gen, count=2)
        replay = parse_blocks(potongan[1])
        assert replay[0]["event"] == "log"
        assert replay[0]["data"]["message"] == "pesan lama"

        handler.emit(_record("pesan baru"))
        live = parse_blocks(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
        assert live[0]["data"]["message"] == "pesan baru"
    finally:
        await gen.aclose()


async def test_logs_stream_tidak_menggandakan_replay() -> None:
    """Baris yang sudah terkirim lewat ring buffer tidak muncul dua kali."""
    bus = EventBus()
    buffer = LogRingBuffer(maxlen=10)
    handler = BusLogHandler(bus, buffer)
    handler.emit(_record("satu"))

    gen = events_router._stream(
        bus, snapshot=lambda: events_router._log_snapshot(buffer), only=frozenset({"log"})
    )
    try:
        await asyncio.wait_for(gen.__anext__(), timeout=1.0)  # retry
        replay = parse_blocks(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
        assert replay[0]["data"]["message"] == "satu"
        last_replayed_id = replay[0]["id"]

        # Event yang sama masih ada di antrean bus; harus dilewati.
        handler.emit(_record("dua"))
        handler.emit(_record("tiga"))
        blok = parse_blocks(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
        assert blok[0]["id"] > last_replayed_id
        assert blok[0]["data"]["message"] in {"dua", "tiga"}
    finally:
        await gen.aclose()


async def test_ring_buffer_menyimpan_id_event() -> None:
    bus = EventBus()
    buffer = LogRingBuffer(maxlen=5)
    BusLogHandler(bus, buffer).emit(_record("berpeng-id"))
    assert buffer.recent()[0]["id"] == 1


# ------------------------------------------- klien lambat tidak memblokir bus


async def test_klien_lambat_tidak_memblokir_penerbit_bus() -> None:
    """Antrean lokal penuh → event dibuang, bukan menahan penerbit (aturan #7)."""
    bus = EventBus(queue_size=10_000, history_size=1)
    gen = events_router._stream(bus, snapshot=lambda: [])
    await asyncio.wait_for(gen.__anext__(), timeout=1.0)  # retry (baris pertama)

    # Klien tidak pernah membaca; antrean lokal (200) akan penuh.
    for index in range(2_000):
        bus.publish("transcript", {"text": f"baris {index}"})  # tidak boleh memblokir

    # Stream harus tetap hidup dan bisa dibaca kembali.
    blok = parse_blocks(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
    assert blok[0]["event"] == "transcript"
    await gen.aclose()


async def test_bus_tidak_memblokir_saat_pelanggan_banyak() -> None:
    """Banyak klien SSE ≠ penerbit lambat: bus tetap menerima semua event."""
    bus = EventBus(queue_size=2)
    streams = [events_router._stream(bus, snapshot=lambda: []) for _ in range(5)]
    for gen in streams:
        await asyncio.wait_for(gen.__anext__(), timeout=1.0)

    for index in range(10):
        bus.publish("status", {"n": index})

    assert bus.dropped > 0  # pengikut lambat kehilangan event, penerbit tidak
    for gen in streams:
        await gen.aclose()
    assert bus.subscriber_count == 0


# ------------------------------------------------------------------- endpoint


def test_stream_membutuhkan_sesi_admin(live_client: TestClient) -> None:
    assert live_client.get("/api/events/stream").status_code == 401
    assert live_client.get("/api/logs/stream").status_code == 401


def _request_for(client: TestClient) -> Any:
    """`Request` palsu yang menunjuk ke state aplikasi yang sedang hidup."""
    return Request({"type": "http", "method": "GET", "path": "/", "app": client.app})


@pytest.mark.parametrize(
    "handler", [events_router.stream_events, events_router.stream_logs]
)
def test_endpoint_stream_menghasilkan_sse_dengan_header_anti_buffer(
    live_client: TestClient, handler: Any
) -> None:
    """Respons streaming tak berujung tak bisa diuji lewat TestClient.

    Router dipanggil langsung: yang diuji adalah tipe media dan header yang
    mencegah proxy membingkai respons.
    """
    do_setup(live_client)
    response = asyncio.run(handler(_admin_session(), _request_for(live_client)))

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"

    async def _pertama() -> str:
        return await response.body_iterator.__anext__()  # type: ignore[union-attr]

    assert asyncio.run(_pertama()).startswith("retry: 3000")


def test_endpoint_stream_terdaftar_di_rute(live_client: TestClient) -> None:
    paths = live_client.app.openapi()["paths"]
    assert "/api/events/stream" in paths
    assert "/api/logs/stream" in paths


def test_log_handler_menyimpan_id_event_di_ring_buffer(live_client: TestClient) -> None:
    """Menyimpan `id` di ring buffer tidak merusak isi payload log."""
    bus: EventBus = live_client.app.state.events
    logging.getLogger("telegent.web.test-sse").warning("halo dari log")

    entries = live_client.app.state.log_buffer.recent(limit=5)
    assert entries, "log harus masuk ke ring buffer"
    assert entries[-1]["message"] == "halo dari log"
    assert "id" in entries[-1]
    assert entries[-1]["id"] == bus.history(limit=1)[-1].id