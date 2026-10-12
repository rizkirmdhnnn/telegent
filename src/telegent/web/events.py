"""Event bus in-process untuk aliran live ke panel web.

Bus bersifat *best-effort*: bila pengikut (subscriber) terlalu lambat, event
dibuang alih-alih memblokir penerbit (runtime bot tidak boleh pernah tersendat
karena Reasonsona UI).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("telegent.web.events")

DEFAULT_QUEUE_SIZE = 200
DEFAULT_HISTORY_SIZE = 200


@dataclass
class Event:
    """Satu event yang dikirim ke panel."""

    id: int
    type: str
    data: dict[str, Any] = field(default_factory=dict)


class Subscription:
    """Aliran event untuk satu pengikut (pendaftaran terjadi saat dibuat)."""

    def __init__(
        self,
        bus: "EventBus",
        queue: "asyncio.Queue[Event]",
        replay: "deque[Event] | None" = None,
    ) -> None:
        self._bus = bus
        self._queue = queue
        self._replay = replay or deque()
        self._closed = False

    def __aiter__(self) -> "Subscription":
        return self

    async def __anext__(self) -> Event:
        if self._closed:
            raise StopAsyncIteration
        if self._replay:
            return self._replay.popleft()
        try:
            return await self._queue.get()
        except asyncio.CancelledError:  # pragma: no cover - koneksi SSE diputus
            await self.aclose()
            raise

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            self._bus.unsubscribe(self._queue)


class EventBus:
    """Publikasi-subscribe sederhana antar task dalam satu event loop."""

    def __init__(
        self,
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        history_size: int = DEFAULT_HISTORY_SIZE,
    ) -> None:
        self._queue_size = queue_size
        self._history: deque[Event] = deque(maxlen=history_size)
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._ids = itertools.count(1)
        self.dropped = 0

    # -------------------------------------------------------------- publish

    def publish(self, event_type: str, data: dict[str, Any] | None = None) -> Event:
        """Terbitkan event ke semua pengikut (dipanggil dari event loop)."""
        event = Event(id=next(self._ids), type=event_type, data=data or {})
        self._history.append(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Pengikut lambat: buang event itu saja, jangan ganggu penerbit.
                self.dropped += 1
        return event

    # ------------------------------------------------------------ subscribe

    def subscribe(self, *, replay: int = 0) -> Subscription:
        """Daftarkan pengikut baru (aktif seketika) dan kembalikan alirannya."""
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        pending = deque(list(self._history)[-replay:]) if replay > 0 else deque()
        return Subscription(self, queue, pending)

    def unsubscribe(self, queue: "asyncio.Queue[Event]") -> None:
        self._subscribers.discard(queue)

    async def stream(self, *, replay: int = 0) -> AsyncIterator[Event]:
        """Bungkus `subscribe()` sebagai async generator."""
        subscription = self.subscribe(replay=replay)
        try:
            while True:
                yield await subscription.__anext__()
        finally:
            await subscription.aclose()

    # -------------------------------------------------------------- utilitas

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def history(self, limit: int | None = None) -> list[Event]:
        events = list(self._history)
        return events[-limit:] if limit else events

    def clear_history(self) -> None:
        self._history.clear()