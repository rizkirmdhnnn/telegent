"""Test event bus & aliran log (tiket A8)."""

from __future__ import annotations

import asyncio
import logging

import pytest

from telegent.web.events import Event, EventBus
from telegent.web.log_stream import (
    BusLogHandler,
    EventLogHandler,
    LogRingBuffer,
    SecretRedactor,
)


async def _kumpulkan(bus: EventBus, jumlah: int, *, replay: int = 0) -> list[Event]:
    """Baca `jumlah` event pertama dari aliran bus."""
    stream = bus.stream(replay=replay)
    hasil: list[Event] = []
    try:
        for _ in range(jumlah):
            hasil.append(await asyncio.wait_for(stream.__anext__(), timeout=1))
    finally:
        await stream.aclose()
    return hasil


# ------------------------------------------------------------------- event bus


async def test_publish_diterima_subscriber() -> None:
    bus = EventBus()
    subscription = bus.subscribe()

    bus.publish("status", {"running": True})
    event = await asyncio.wait_for(subscription.__anext__(), timeout=1)
    await subscription.aclose()

    assert event.type == "status"
    assert event.data == {"running": True}
    assert event.id == 1


async def test_beberapa_subscriber_menerima_event_sama() -> None:
    bus = EventBus()
    a = bus.subscribe()
    b = bus.subscribe()

    bus.publish("log", {"message": "hai"})
    event_a, event_b = await asyncio.wait_for(
        asyncio.gather(a.__anext__(), b.__anext__()), timeout=1
    )
    await a.aclose()
    await b.aclose()

    assert event_a.id == event_b.id


async def test_subscriber_lambat_tidak_memblok_penerbit() -> None:
    bus = EventBus(queue_size=2)
    subscription = bus.subscribe()  # aktif tapi tidak pernah dibaca
    assert bus.subscriber_count == 1

    # Terbitkan jauh melebihi ukuran antrean; penerbit tidak boleh tersendat.
    for index in range(10):
        bus.publish("log", {"n": index})

    assert bus.dropped > 0
    await subscription.aclose()
    assert bus.subscriber_count == 0


async def test_replay_mengirim_riwayat_terakhir() -> None:
    bus = EventBus(history_size=5)
    for index in range(8):
        bus.publish("call.ended", {"n": index})

    hasil = await _kumpulkan(bus, 3, replay=3)
    assert [event.data["n"] for event in hasil] == [5, 6, 7]


async def test_riwayat_terbatas_dan_bisa_dikosongkan() -> None:
    bus = EventBus(history_size=2)
    for index in range(5):
        bus.publish("x", {"n": index})

    assert len(bus.history()) == 2
    assert bus.history(limit=1)[0].data == {"n": 4}

    bus.clear_history()
    assert bus.history() == []


async def test_stream_berhenti_bersih_saat_dibatalkan() -> None:
    bus = EventBus()
    stream = bus.stream()
    await stream.aclose()
    assert bus.subscriber_count == 0


# ------------------------------------------------------------------- redactor


def test_redactor_mengganti_nilai_secret() -> None:
    redactor = SecretRedactor(["AIzaSy0123456789012345", "0123456789abcdef0123456789abcdef"])

    teks = "gagal login dengan AIzaSy0123456789012345 (hash 0123456789abcdef0123456789abcdef)"
    hasil = redactor.redact(teks)

    assert "AIzaSy0123456789012345" not in hasil
    assert "0123456789abcdef0123456789abcdef" not in hasil
    assert hasil.count("[REDACTED]") == 2


def test_redactor_mengabaikan_nilai_pendek_dan_kosong() -> None:
    redactor = SecretRedactor(["abc", "", None])
    redactor.add(None)
    assert redactor.redact("nilai pendek abc tetap") == "nilai pendek abc tetap"


def test_redactor_bisa_dikosongkan() -> None:
    redactor = SecretRedactor(["AIzaSy0123456789012345"])
    redactor.clear()
    assert redactor.redact("AIzaSy0123456789012345") == "AIzaSy0123456789012345"


# --------------------------------------------------------------- log handler


def _record(level: int = logging.INFO, message: str = "halo", args=()) -> logging.LogRecord:
    return logging.LogRecord(
        name="telegent.call",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=None,
    )


async def test_event_log_handler_meneruskan_record() -> None:
    bus = EventBus()
    handler = EventLogHandler(bus)
    handler.emit(_record(logging.WARNING, "peringatan %s", ("besar",)))

    event = bus.history()[-1]
    assert event.type == "log"
    assert event.data["level"] == "WARNING"
    assert event.data["logger"] == "telegent.call"
    assert event.data["message"] == "peringatan besar"
    assert event.data["at"].endswith("Z")


async def test_event_log_handler_menyaring_secret() -> None:
    bus = EventBus()
    handler = EventLogHandler(bus, SecretRedactor(["AIzaSy0123456789012345"]))
    handler.emit(_record(message="memakai kunci AIzaSy0123456789012345"))

    assert "AIzaSy0123456789012345" not in bus.history()[-1].data["message"]
    assert "[REDACTED]" in bus.history()[-1].data["message"]


async def test_event_log_handler_tahan_record_rusak() -> None:
    bus = EventBus()
    handler = EventLogHandler(bus)
    handler.handleError = lambda record: None  # type: ignore[assignment]

    record = _record(message="jumlah %d")
    record.args = ("bukan-angka",)  # memunculkan galat saat formatting

    handler.emit(record)  # tidak boleh melempar
    assert bus.history()[-1].data["message"] == "jumlah %d"


async def test_bus_log_handler_menyimpan_ke_ring_buffer() -> None:
    bus = EventBus()
    buffer = LogRingBuffer(maxlen=2)
    handler = BusLogHandler(bus, buffer)

    for index in range(5):
        handler.emit(_record(message=f"pesan {index}"))

    assert len(buffer) == 2
    assert [item["message"] for item in buffer.recent()] == ["pesan 3", "pesan 4"]
    assert bus.history()[-1].data["message"] == "pesan 4"


def test_ring_buffer_batas_dan_urutan() -> None:
    buffer = LogRingBuffer(maxlen=3)
    for index in range(5):
        buffer.add({"n": index})

    assert [item["n"] for item in buffer.recent()] == [2, 3, 4]
    assert buffer.recent(limit=1) == [{"n": 4}]


# --------------------------------------------------------------- integrasi app


def test_bus_dipasang_pada_lifespan(live_client) -> None:
    bus = live_client.app.state.events
    assert isinstance(bus, EventBus)
    assert live_client.app.state.log_buffer is not None
    assert isinstance(live_client.app.state.redactor, SecretRedactor)


def test_handler_log_dilepas_setelah_shutdown(bootstrap) -> None:
    from starlette.testclient import TestClient

    from telegent.web.app import create_app

    before = len(logging.getLogger().handlers)
    with TestClient(create_app(bootstrap)) as client:
        during = len(logging.getLogger().handlers)
        assert client.get("/api/healthz").status_code == 200

    assert during == before + 1
    assert len(logging.getLogger().handlers) == before


async def test_event_runtime_terhubung_ke_bus(live_client) -> None:
    """Status runtime bisa diteruskan ke bus untuk ditampilkan UI."""
    bus: EventBus = live_client.app.state.events
    controller = live_client.app.state.runtime

    bus.publish("status", controller.status().to_dict())

    event = bus.history()[-1]
    assert event.type == "status"
    assert event.data["state"] == "stopped"


@pytest.mark.parametrize("size", [1, 5, 50])
async def test_ukuran_antrean_bisa_diatur(size: int) -> None:
    bus = EventBus(queue_size=size)
    subscription = bus.subscribe()
    for index in range(size * 3):
        bus.publish("x", {"n": index})
    await subscription.aclose()
    assert bus.subscriber_count == 0