"""Penyalinan log Python ke event bus + penyaringan nilai secret."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Iterable

from telegent.web.db.base import utcnow
from telegent.web.events import EventBus

log = logging.getLogger("telegent.web.logstream")

MIN_REDACT_LENGTH = 8


class SecretRedactor:
    """Ganti kemunculan nilai secret di dalam teks log dengan penanda."""

    def __init__(self, values: Iterable[str | None] = ()) -> None:
        self._values: set[str] = set()
        self.add_all(values)

    def add(self, value: str | None) -> None:
        if value and len(value) >= MIN_REDACT_LENGTH:
            self._values.add(value)

    def add_all(self, values: Iterable[str | None]) -> None:
        for value in values:
            self.add(value)

    def clear(self) -> None:
        self._values.clear()

    def __call__(self, text: str) -> str:
        return self.redact(text)

    def redact(self, text: str) -> str:
        for value in self._values:
            if value in text:
                text = text.replace(value, "[REDACTED]")
        return text


class EventLogHandler(logging.Handler):
    """Handler logging yang meneruskan record ke `EventBus` sebagai event `log`."""

    def __init__(
        self,
        bus: EventBus,
        redactor: SecretRedactor | None = None,
        *,
        level: int = logging.NOTSET,
    ) -> None:
        super().__init__(level=level)
        self._bus = bus
        self._redactor = redactor

    def _payload(self, record: logging.LogRecord) -> dict[str, Any]:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - format record rusak
            message = str(record.msg)
        if self._redactor is not None:
            message = self._redactor.redact(message)
        return {
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "at": utcnow().isoformat() + "Z",
        }

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._bus.publish("log", self._payload(record))
        except Exception:  # noqa: BLE001 - logging tidak boleh melempar
            self.handleError(record)


class LogRingBuffer:
    """Penyimpanan log terakhir untuk dikirim ke klien yang baru terhubung."""

    def __init__(self, maxlen: int = 1000) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=max(1, maxlen))

    def add(self, entry: dict[str, Any]) -> None:
        self._entries.append(entry)

    def recent(self, limit: int | None = None) -> list[dict[str, Any]]:
        entries = list(self._entries)
        return entries[-limit:] if limit else entries

    def __len__(self) -> int:
        return len(self._entries)


class BusLogHandler(EventLogHandler):
    """Handler yang mengirim ke bus sekaligus menyalin ke ring buffer."""

    def __init__(
        self,
        bus: EventBus,
        buffer: LogRingBuffer,
        redactor: SecretRedactor | None = None,
    ) -> None:
        super().__init__(bus, redactor)
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = self._payload(record)
            # Terbitkan lebih dulu agar ring buffer bisa menyimpan id event:
            # SSE memakai id itu untuk melewati entri yang sudah di-replay.
            event = self._bus.publish("log", payload)
            self._buffer.add({**payload, "id": event.id})
        except Exception:  # noqa: BLE001
            self.handleError(record)