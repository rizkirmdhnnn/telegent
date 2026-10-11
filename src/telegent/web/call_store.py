"""Penyimpanan riwayat panggilan, transkrip, dan tool call (spesifikasi §5.5–5.7).

Pola sama seperti `tools_store.py`/`telegram_store.py`: fungsi repo murni yang
hanya menyentuh database, tanpa event bus maupun task background. Dengan begitu
`CallRecorder` yang menjembatani ke EventBus tetap tipis, dan seluruh akses DB
dapat diuji tanpa jaringan maupun event loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from telegent.telegram.call_session import (
    END_REASON_CALLER,
    END_REASON_ERROR,
    END_REASON_REJECTED,
    OUTCOME_ANSWERED,
    OUTCOME_ERROR,
    OUTCOME_PENDING,
    OUTCOME_REJECTED_CAPACITY,
    OUTCOME_REJECTED_DUPLICATE,
    OUTCOME_REJECTED_RATELIMIT,
    OUTCOME_REJECTED_WHITELIST,
)
from telegent.web.db import models
from telegent.web.db.base import Database, utcnow

log = logging.getLogger("telegent.web.call_store")

#: Outcome & end_reason berasal dari `call_session` (satu sumber kebenaran).
ALL_OUTCOMES = (
    OUTCOME_PENDING,
    OUTCOME_ANSWERED,
    OUTCOME_REJECTED_WHITELIST,
    OUTCOME_REJECTED_RATELIMIT,
    OUTCOME_REJECTED_CAPACITY,
    OUTCOME_REJECTED_DUPLICATE,
    OUTCOME_ERROR,
)

#: Pembicara transkrip (spesifikasi §5.6).
SPEAKER_CALLER = "caller"
SPEAKER_AI = "ai"

#: Batas aman untuk teks yang disimpan (mencegah satu utterance raksasa).
MAX_TEXT_LEN = 8000
MAX_JSON_LEN = 16000


def dumps_json(value: Any, *, limit: int = MAX_JSON_LEN) -> str | None:
    """Serialisasi JSON dengan pemotongan aman bila nilai terlalu besar."""
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # nilai tidak bisa diserialisasi (mis. bytes)
        text = json.dumps(str(value), ensure_ascii=False)
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


# ------------------------------------------------------------------ call record


async def start_call(
    db: Database,
    *,
    tg_call_id: int,
    user_id: int,
    user_display: str | None = None,
    outcome: str = OUTCOME_PENDING,
    started_at: datetime | None = None,
) -> int:
    """Buat `call_record` saat panggilan masuk; kembalikan id barisnya."""
    async with db.session() as session:
        row = models.CallRecord(
            tg_call_id=tg_call_id,
            user_id=user_id,
            user_display=user_display,
            outcome=outcome,
            started_at=started_at or utcnow(),
        )
        session.add(row)
        await session.flush()
        return int(row.id)


async def mark_call_started(
    db: Database, record_id: int, *, started_at: datetime | None = None
) -> None:
    """Tandai `started_at` saat panggilan benar-benar aktif (media siap).

    Record sudah dibuat sejak panggilan masuk (Q12); pemindahan `started_at`
    membuat `duration_sec` konsisten dengan durasi sesi yang diukur runtime.
    """
    async with db.session() as session:
        row = await session.get(models.CallRecord, record_id)
        if row is not None:
            row.started_at = started_at or utcnow()


async def finish_call(
    db: Database,
    record_id: int,
    *,
    outcome: str,
    end_reason: str | None = None,
    duration_sec: int | None = None,
    ended_at: datetime | None = None,
    transcript_count: int | None = None,
    tool_call_count: int | None = None,
) -> None:
    """Tutup `call_record`: waktu akhir, durasi, alasan, dan jumlah isi."""
    async with db.session() as session:
        row = await session.get(models.CallRecord, record_id)
        if row is None:
            return
        ended = ended_at or utcnow()
        row.ended_at = ended
        row.outcome = outcome
        row.end_reason = end_reason
        row.duration_sec = max(0, duration_sec or 0)
        if transcript_count is not None:
            row.transcript_count = max(0, transcript_count)
        if tool_call_count is not None:
            row.tool_call_count = max(0, tool_call_count)


async def bump_call_counts(
    db: Database,
    record_id: int,
    *,
    transcripts: int = 0,
    tool_calls: int = 0,
) -> None:
    """Naikkan penghitung isi panggilan (supaya UI melihat angka saat berjalan).

    Penulisan akhir tetap memastekan nilai absolut lewat `finish_call`, sehingga
    penghitung tidak pernah menyimpang meski ada pengulangan event.
    """
    if not transcripts and not tool_calls:
        return
    values: dict[str, Any] = {}
    if transcripts:
        values["transcript_count"] = models.CallRecord.transcript_count + transcripts
    if tool_calls:
        values["tool_call_count"] = models.CallRecord.tool_call_count + tool_calls
    async with db.session() as session:
        await session.execute(
            update(models.CallRecord).where(models.CallRecord.id == record_id).values(**values)
        )


async def find_by_tg_call_id(db: Database, tg_call_id: int) -> int | None:
    async with db.session() as session:
        return await session.scalar(
            select(models.CallRecord.id)
            .where(models.CallRecord.tg_call_id == tg_call_id)
            .order_by(models.CallRecord.id.desc())
            .limit(1)
        )


# ------------------------------------------------------------------- transcript


async def add_transcript(
    db: Database,
    call_record_id: int,
    *,
    speaker: str,
    text: str,
    at: datetime | None = None,
) -> int | None:
    """Simpan satu baris transkrip; `None` bila record induk sudah tidak ada."""
    clean = text.strip()
    if not clean:
        return None
    async with db.session() as session:
        row = models.TranscriptEntry(
            call_record_id=call_record_id,
            speaker=speaker,
            text=clean[:MAX_TEXT_LEN],
            at=at or utcnow(),
        )
        session.add(row)
        await session.flush()
        return int(row.id)


# -------------------------------------------------------------------- tool call


async def add_tool_call(
    db: Database,
    call_record_id: int,
    *,
    name: str,
    args_json: str | None = None,
    result_json: str | None = None,
    status: str = "ok",
    duration_ms: int = 0,
    at: datetime | None = None,
) -> int | None:
    """Simpan satu pemanggilan tool beserta argumen, hasil, dan durasinya."""
    async with db.session() as session:
        row = models.ToolCallRecord(
            call_record_id=call_record_id,
            name=name[:64],
            args_json=args_json,
            result_json=result_json,
            status=status,
            duration_ms=max(0, duration_ms),
            at=at or utcnow(),
        )
        session.add(row)
        await session.flush()
        return int(row.id)


# ------------------------------------------------------------------------ baca


@dataclass(frozen=True)
class CallFilters:
    """Filter riwayat panggilan (spesifikasi §6.6)."""

    page: int = 1
    page_size: int = 20
    from_at: datetime | None = None
    to_at: datetime | None = None
    user_id: int | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class CallPage:
    """Hasil satu halaman riwayat beserta totalnya."""

    items: list[models.CallRecord]
    total: int
    page: int
    page_size: int


def _filter_conditions(filters: CallFilters) -> list[Any]:
    """Syarat WHERE dari filter riwayat (dipakai daftar & ekspor)."""
    conditions: list[Any] = []
    if filters.from_at is not None:
        conditions.append(models.CallRecord.started_at >= filters.from_at)
    if filters.to_at is not None:
        conditions.append(models.CallRecord.started_at <= filters.to_at)
    if filters.user_id is not None:
        conditions.append(models.CallRecord.user_id == filters.user_id)
    if filters.outcome:
        conditions.append(models.CallRecord.outcome == filters.outcome)
    return conditions


async def list_calls(db: Database, filters: CallFilters) -> CallPage:
    """Halaman riwayat panggilan (terbaru dulu) + total baris yang cocok."""
    count_stmt = select(func.count()).select_from(models.CallRecord)
    stmt = select(models.CallRecord)
    for condition in _filter_conditions(filters):
        count_stmt = count_stmt.where(condition)
        stmt = stmt.where(condition)

    offset = (filters.page - 1) * filters.page_size
    async with db.session() as session:
        total = int((await session.execute(count_stmt)).scalar_one())
        rows = (
            (
                await session.execute(
                    stmt.order_by(
                        models.CallRecord.started_at.desc(), models.CallRecord.id.desc()
                    )
                    .offset(offset)
                    .limit(filters.page_size)
                )
            )
            .scalars()
            .all()
        )
    return CallPage(
        items=list(rows), total=total, page=filters.page, page_size=filters.page_size
    )


async def calls_for_export(
    db: Database, filters: CallFilters, *, limit: int = 10000
) -> list[models.CallRecord]:
    """Semua baris yang cocok untuk ekspor CSV (tanpa paginasi, dibatasi)."""
    stmt = select(models.CallRecord)
    for condition in _filter_conditions(filters):
        stmt = stmt.where(condition)
    stmt = stmt.order_by(
        models.CallRecord.started_at.desc(), models.CallRecord.id.desc()
    ).limit(limit)
    async with db.session() as session:
        rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def get_call(db: Database, record_id: int) -> models.CallRecord | None:
    """Detail satu `call_record`; `None` bila tidak ada."""
    async with db.session() as session:
        # `selectinload` wajib: accessing `transcripts`/`tool_calls` di dalam
        # konteks async tanpa eager load memicu MissingGreenlet (aturan #7).
        stmt = (
            select(models.CallRecord)
            .options(selectinload(models.CallRecord.transcripts))
            .where(models.CallRecord.id == record_id)
        )
        return (await session.execute(stmt)).scalars().first()


async def list_transcripts(db: Database, record_id: int) -> list[models.TranscriptEntry]:
    """Transkrip satu panggilan, urut waktu (lama ke baru)."""
    async with db.session() as session:
        rows = (
            (
                await session.execute(
                    select(models.TranscriptEntry)
                    .where(models.TranscriptEntry.call_record_id == record_id)
                    .order_by(models.TranscriptEntry.at, models.TranscriptEntry.id)
                )
            )
            .scalars()
            .all()
        )
    return list(rows)


async def list_tool_calls(db: Database, record_id: int) -> list[models.ToolCallRecord]:
    """Riwayat tool call satu panggilan, urut waktu."""
    async with db.session() as session:
        rows = (
            (
                await session.execute(
                    select(models.ToolCallRecord)
                    .where(models.ToolCallRecord.call_record_id == record_id)
                    .order_by(models.ToolCallRecord.at, models.ToolCallRecord.id)
                )
            )
            .scalars()
            .all()
        )
    return list(rows)