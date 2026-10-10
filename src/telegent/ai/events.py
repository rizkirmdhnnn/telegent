"""Event netral yang dihasilkan oleh sesi suara AI (tidak terikat tipe Gemini)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


@dataclass(frozen=True)
class AudioOut:
    """Potongan audio jawaban AI (PCM 24 kHz mono 16-bit)."""

    pcm24k: bytes


@dataclass(frozen=True)
class TranscriptIn:
    """Transkripsi ucapan penelpon."""

    text: str


@dataclass(frozen=True)
class TranscriptOut:
    """Transkripsi ucapan AI."""

    text: str


@dataclass(frozen=True)
class Interrupted:
    """Penelpon memotong ucapan AI (barge-in)."""


@dataclass(frozen=True)
class TurnComplete:
    """Server menandai satu giliran model selesai."""


@dataclass(frozen=True)
class ToolCallEvent:
    """Model meminta eksekusi sebuah fungsi/tool."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolCallCancelled:
    """Server membatalkan tool call (mis. karena interupsi)."""

    id: str


LiveEvent = Union[
    AudioOut,
    TranscriptIn,
    TranscriptOut,
    Interrupted,
    TurnComplete,
    ToolCallEvent,
    ToolCallCancelled,
]
