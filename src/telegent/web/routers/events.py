"""Endpoint SSE: aliran event status/panggilan & log live (spesifikasi §6.8).

Keputusan penting:

* **Heartbeat 15 detik** dikirim sebagai komentar SSE (`: ping`), bukan event:
  proxy tidak memutus koneksi yang sunyi, dan `EventSource` di browser tidak
  memicu handler apa pun.
* **Publikasi tidak pernah menunggu klien.** Setiap stream punya *pump* task yang
  membaca antrean bus lalu menuliskannya ke antrean lokal berbatas; saat antrean
  lokal penuh, event dibuang, bukan menahan penerbit (catatan §7).
* `retry:` dikirim di awal sehingga klien tahu jeda reconnect (3 detik).
* Klien baru menerima replay riwayat: riwayat bus untuk event, ring buffer log
  untuk log. Snapshot diambil **setelah** subscribe supaya tidak ada celah event
  yang hilang, dan event yang sudah terkirim lewat replay dilewati.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from telegent.web.deps import AdminDep
from telegent.web.events import Event, EventBus, Subscription
from telegent.web.log_stream import LogRingBuffer

log = logging.getLogger("telegent.web.events_router")

router = APIRouter(tags=["events"])

#: Jeda reconnect yang saran ke browser.
SSE_RETRY_MS = 3000

#: Interval heartbeat; mencegah proxy memutus koneksi yang sunyi.
HEARTBEAT_SEC = 15.0

#: Berapa banyak entri riwayat yang dikirim ke klien yang baru terhubung.
DEFAULT_REPLAY = 100

#: Batas antrean lokal per klien. Setelah penuh, event dibuang — penerbit bus
#: (bot) tidak boleh pernah tersendat karena satu tab browser yang lambat.
LOCAL_QUEUE_SIZE = 200

#: Tipe event untuk log (dipakai juga oleh `BusLogHandler`).
LOG_EVENT = "log"

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    # Mematikan buffering proxy perantara agar event benar-benar "live".
    "X-Accel-Buffering": "no",
}


def format_event(event: Event) -> str:
    """Satu blok SSE: `id`, `event`, dan `data` JSON."""
    payload = json.dumps(event.data, ensure_ascii=False, default=str)
    return f"id: {event.id}\nevent: {event.type}\ndata: {payload}\n\n"


async def _pump(
    subscription: Subscription,
    sink: "asyncio.Queue[Event | None]",
    only: frozenset[str],
    without: frozenset[str],
) -> None:
    """Teruskan event bus → antrean lokal; lewati saat antrean lokal penuh.

    Antrean lokal sengaja dibatasi: klien lambat menyebabkan event *buang* di
    sisi klien, sementara antrean bus (yang ditunggu penerbit) tetap kosong.
    """
    try:
        async for event in subscription:
            if event.type in without or (only and event.type not in only):
                continue
            if not sink.full():
                await sink.put(event)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - kegagalan satu klien tidak boleh fatal
        log.exception("Aliran SSE terganggu.")
    finally:
        with suppress(asyncio.QueueFull):
            sink.put_nowait(None)


async def _stream(
    bus: EventBus,
    *,
    snapshot: Callable[[], list[Event]],
    only: frozenset[str] = frozenset(),
    without: frozenset[str] = frozenset(),
) -> AsyncIterator[str]:
    """Generator SSE: replay → event langsung → heartbeat.

    Subscribe dilakukan **sebelum** snapshot, lalu event langsung yang id-nya
    sudah tercakup replay dilewati agar tidak dobel.
    """
    subscription = bus.subscribe()
    replay = snapshot()
    last_replay_id = max((event.id for event in replay), default=0)

    sink: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=LOCAL_QUEUE_SIZE)
    pump = asyncio.create_task(
        _pump(subscription, sink, only, without), name="telegent-sse-pump"
    )
    try:
        yield f"retry: {SSE_RETRY_MS}\n\n"
        for event in replay:
            yield format_event(event)
        while True:
            try:
                event = await asyncio.wait_for(sink.get(), timeout=HEARTBEAT_SEC)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if event is None:
                break
            if event.id <= last_replay_id:
                continue  # sudah terkirim lewat replay
            yield format_event(event)
    except asyncio.CancelledError:
        # Klien menutup tab / proxy memutus koneksi: normal, bukan galat.
        raise
    finally:
        pump.cancel()
        with suppress(asyncio.CancelledError):
            await pump
        await subscription.aclose()


def _sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream", headers=SSE_HEADERS)


def _log_snapshot(buffer: LogRingBuffer, limit: int = DEFAULT_REPLAY) -> list[Event]:
    """Ring buffer log → daftar event agar lewat formatter yang sama."""
    return [
        Event(id=int(entry.get("id") or 0), type=LOG_EVENT, data=entry)
        for entry in buffer.recent(limit=limit)
    ]


@router.get("/events/stream")
async def stream_events(admin: AdminDep, request: Request) -> StreamingResponse:
    """Aliran status runtime, panggilan, transkrip, dan tool call (bukan log)."""
    del admin
    bus: EventBus = request.app.state.events
    return _sse_response(
        _stream(
            bus,
            snapshot=lambda: [
                event
                for event in bus.history(limit=DEFAULT_REPLAY)
                if event.type != LOG_EVENT
            ],
            without=frozenset({LOG_EVENT}),
        )
    )


@router.get("/logs/stream")
async def stream_logs(admin: AdminDep, request: Request) -> StreamingResponse:
    """Aliran log: ring buffer awal, lalu log langsung tanpa duplikat."""
    del admin
    bus: EventBus = request.app.state.events
    buffer: LogRingBuffer = request.app.state.log_buffer
    return _sse_response(
        _stream(bus, snapshot=lambda: _log_snapshot(buffer), only=frozenset({LOG_EVENT}))
    )


__all__ = ["router", "format_event", "HEARTBEAT_SEC", "SSE_RETRY_MS"]