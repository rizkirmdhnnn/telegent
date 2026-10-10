"""Interface (seam) agar komponen inti dapat diuji tanpa dependensi berat."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, Sequence, runtime_checkable

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

    async def send_tool_response(self, responses: Sequence[ToolResponse]) -> None:
        ...

    def events(self) -> AsyncIterator[LiveEvent]:
        ...

    async def close(self) -> None:
        ...
