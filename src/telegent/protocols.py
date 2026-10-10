"""Interface (seam) agar komponen inti dapat diuji tanpa dependensi berat."""

from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, Sequence, runtime_checkable

from telegent.ai.events import LiveEvent
from telegent.ai.tools.spec import ToolResponse


@runtime_checkable
class AudioSink(Protocol):
    """Tujuan pengiriman audio keluar (mis. ntgcalls)."""

    async def send_frame(self, frame: bytes) -> None:
        ...


@runtime_checkable
class LiveVoiceSession(Protocol):
    """Sesi AI dua arah (mis. Gemini Live)."""

    async def send_audio(self, pcm16k: bytes) -> None:
        ...

    async def send_greeting(self, prompt: str) -> None:
        ...

    async def send_prompt(self, text: str) -> None:
        ...

    async def send_tool_response(self, responses: Sequence[ToolResponse]) -> None:
        ...

    def events(self) -> AsyncIterator[LiveEvent]:
        ...

    async def close(self) -> None:
        ...


@runtime_checkable
class CallObserver(Protocol):
    """Pemantau siklus hidup satu panggilan (mis. panel web — tiket E1).

    Seluruh metode **sinkron dan wajib non-memblokir**: dipanggil dari event
    loop yang sama dengan jalur audio 10 ms, jadi implementasinya hanya boleh
    mengantrekan pekerjaan, bukan melakukan I/O.
    """

    def call_incoming(
        self, tg_call_id: int, user_id: int, *, user_display: str | None = None
    ) -> None:
        """Panggilan masuk diterima bot — termasuk yangkemudian ditolak."""

    def call_started(self, tg_call_id: int, user_id: int) -> None:
        """Mediadan sesi AI siap; panggilan sudah aktif."""

    def call_ended(
        self,
        tg_call_id: int,
        user_id: int,
        *,
        outcome: str,
        end_reason: str | None = None,
        duration_sec: int | None = None,
    ) -> None:
        """Panggilan selesai (dijawab, ditolak, atau gagal)."""

    def session_event(self, tg_call_id: int, event: str, data: dict[str, Any]) -> None:
        """Peristiwa sesi: `transcript` atau `tool_call`."""
