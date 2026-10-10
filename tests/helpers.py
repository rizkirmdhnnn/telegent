"""Helper (fake) untuk pengujian tanpa dependensi jaringan/native."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from telegent.ai.tools.registry import ToolRegistry
from telegent.config import Settings
from telegent.telegram.call_session import CallSession


class FakeLiveSession:
    """LiveVoiceSession tiruan yang mengalirkan event yang sudah ditentukan."""

    def __init__(self, events=None) -> None:
        self._events = list(events or [])
        self.audio_sent: list[bytes] = []
        self.greetings: list[str] = []
        self.prompts: list[str] = []
        self.tool_responses: list = []
        self.closed = False

    async def send_audio(self, pcm16k: bytes) -> None:
        self.audio_sent.append(pcm16k)

    async def send_greeting(self, prompt: str) -> None:
        self.greetings.append(prompt)

    async def send_prompt(self, text: str) -> None:
        self.prompts.append(text)

    async def send_tool_response(self, responses) -> None:
        self.tool_responses.extend(responses)

    async def events(self):
        for event in self._events:
            yield event

    async def close(self) -> None:
        self.closed = True


class FakeSink:
    """AudioSink tiruan yang merekam frame yang dikirim."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []

    async def send_frame(self, frame: bytes) -> None:
        self.frames.append(frame)


def make_session(
    *,
    settings: Settings,
    live: FakeLiveSession,
    sink: FakeSink | None = None,
    tools: ToolRegistry | None = None,
) -> CallSession:
    @asynccontextmanager
    async def factory():
        yield live

    return CallSession(
        user_id=1,
        call_id=1,
        access_hash=1,
        sink=sink or FakeSink(),
        live_factory=factory,
        tools=tools or ToolRegistry(),
        settings=settings,
        logger=logging.getLogger("test"),
    )
