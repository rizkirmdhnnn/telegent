"""Skema data untuk endpoint pemantauan panggilan & SSE (spesifikasi §6.6, §6.8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActiveCall(BaseModel):
    """Satu panggilan yang sedang berjalan (live dari runtime)."""

    record_id: int | None = Field(
        default=None, description="Id `call_record`; None bila belum tercatat"
    )
    user_id: int
    tg_call_id: int
    state: str = Field(description="Status sesi: INCOMING_CALL/CONNECTING/ACTIVE/ENDING")
    duration_sec: int = 0
    transcript_tail: list[dict[str, Any]] = Field(default_factory=list)


class ActiveCallListResponse(BaseModel):
    """Respons `/calls/active`; daftar kosong bila bot tidak berjalan."""

    calls: list[ActiveCall] = Field(default_factory=list)
    count: int = 0


class CallSummary(BaseModel):
    """Satu baris riwayat panggilan."""

    id: int
    tg_call_id: int
    user_id: int
    user_display: str | None = None
    outcome: str
    end_reason: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_sec: int | None = None
    transcript_count: int = 0
    tool_call_count: int = 0


class CallListResponse(BaseModel):
    """Respons `/calls`: satu halaman riwayat beserta totalnya."""

    items: list[CallSummary] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 0


class CallDetail(CallSummary):
    """Respons `/calls/{id}`."""

    active: bool = Field(
        default=False, description="True bila panggilan masih berjalan saat dibaca"
    )


class TranscriptItem(BaseModel):
    """Satu baris transkrip."""

    id: int
    speaker: str
    text: str
    at: datetime


class TranscriptListResponse(BaseModel):
    """Respons `/calls/{id}/transcript`."""

    items: list[TranscriptItem] = Field(default_factory=list)
    total: int = 0


class ToolCallItem(BaseModel):
    """Satu pemanggilan tool beserta argumen, hasil, dan durasinya."""

    id: int
    name: str
    args: Any = None
    result: Any = None
    status: str
    duration_ms: int
    at: datetime


class ToolCallListResponse(BaseModel):
    """Respons `/calls/{id}/tools`."""

    items: list[ToolCallItem] = Field(default_factory=list)
    total: int = 0