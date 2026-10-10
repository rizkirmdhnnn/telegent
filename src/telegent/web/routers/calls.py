"""Router pemantauan panggilan (spesifikasi §6.6, tiket E2).

Semua endpoint **hanya-baca** kecuali `hangup`: tidak ada penulisan database
di dalam `GET` (aturan rekayasa #3), dan mutasi selalu memakai sesi admin + CSRF.
Bot yang tidak berjalan bukan galat — `/calls/active` mengembalikan daftar kosong.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from telegent.telegram.call_session import END_REASON_PANEL, CallSession
from telegent.web.audit import AuditEntry, record_audit
from telegent.web.call_store import (
    ALL_OUTCOMES,
    CallFilters,
    calls_for_export,
    get_call,
    list_calls,
    list_tool_calls,
    list_transcripts,
)
from telegent.web.db import models
from telegent.web.deps import AdminDep, CallRecorderDep, CsrfDep, DatabaseDep, RuntimeDep
from telegent.web.errors import APIError
from telegent.web.runtime import RuntimeController
from telegent.web.schemas.base import SimpleOkResponse
from telegent.web.schemas.calls import (
    ActiveCall,
    ActiveCallListResponse,
    CallDetail,
    CallListResponse,
    CallSummary,
    ToolCallItem,
    ToolCallListResponse,
    TranscriptItem,
    TranscriptListResponse,
)

router = APIRouter(prefix="/calls", tags=["calls"])

#: Nama berkas hasil ekspor (Q14).
EXPORT_FILENAME = "telegent-calls.csv"

#: Jumlah baris maksimum satu ekspor (proteksi memori bila data sangat banyak).
EXPORT_LIMIT = 10000

#: Kolom ekspor CSV (urutan tetap agar hasil ekspor stabil & mudah dibandingkan).
EXPORT_COLUMNS = (
    "id",
    "tg_call_id",
    "user_id",
    "user_display",
    "outcome",
    "end_reason",
    "started_at",
    "ended_at",
    "duration_sec",
    "transcript_count",
    "tool_call_count",
)

#: Target audit: satu panggilan, bukan nama berkas sesi.
AUDIT_TARGET = "call"


# --------------------------------------------------------------------- utilitas


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _iso(value: datetime | None) -> str | None:
    return f"{value.isoformat()}Z" if value is not None else None


def _parse_dt(value: str | None, *, field: str) -> datetime | None:
    """Parse parameter waktu (`YYYY-MM-DD` atau ISO penuh) menjadi naive UTC.

    Nilai dengan offset dikonversi ke UTC agar konsisten dengan kolom database
    yang disimpan sebagai waktu UTC tanpa zona.
    """
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise APIError(
            422, "invalid_filter", f"Parameter '{field}' bukan tanggal yang valid."
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz=None).replace(tzinfo=None)
    return parsed


def _filters(
    page: int,
    page_size: int,
    date_from: str | None,
    date_to: str | None,
    user: int | None,
    outcome: str | None,
) -> CallFilters:
    if outcome and outcome not in ALL_OUTCOMES:
        raise APIError(422, "invalid_filter", f"Outcome '{outcome}' tidak dikenal.")
    return CallFilters(
        page=page,
        page_size=page_size,
        from_at=_parse_dt(date_from, field="from"),
        to_at=_parse_dt(date_to, field="to"),
        user_id=user,
        outcome=outcome,
    )


def _summary(row: models.CallRecord) -> CallSummary:
    return CallSummary(
        id=row.id,
        tg_call_id=row.tg_call_id,
        user_id=row.user_id,
        user_display=row.user_display,
        outcome=row.outcome,
        end_reason=row.end_reason,
        started_at=row.started_at,
        ended_at=row.ended_at,
        duration_sec=row.duration_sec,
        transcript_count=row.transcript_count,
        tool_call_count=row.tool_call_count,
    )


def _decode(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


async def _require_call(db: DatabaseDep, record_id: int) -> models.CallRecord:
    """Ambil record atau gagalkan dengan 404 yang konsisten."""
    row = await get_call(db, record_id)
    if row is None:
        raise APIError(404, "call_not_found", "Panggilan tidak ditemukan.")
    return row


def _find_session(runtime: RuntimeController, row: models.CallRecord) -> CallSession | None:
    """Sesi aktif untuk satu record; `None` bila panggilan sudah selesai."""
    return runtime.find_session_by_call_id(row.tg_call_id)


# --------------------------------------------------------------- panggilan aktif


@router.get("/active", response_model=ActiveCallListResponse)
async def list_active_calls(
    admin: AdminDep,
    runtime: RuntimeDep,
    recorder: CallRecorderDep,
) -> ActiveCallListResponse:
    """Sesi panggilan yang sedang berjalan (live dari runtime, tanpa DB).

    Bot yang sedang berhenti tidak punya sesi — hasilnya daftar kosong, bukan
    galat, sehingga dashboard tidak perlu dua jalur penanganan error.
    """
    del admin
    calls = [
        ActiveCall(
            record_id=recorder.record_id_for(session.call_id),
            user_id=session.user_id,
            tg_call_id=session.call_id,
            state=session.state.value,
            duration_sec=session.duration_seconds,
            transcript_tail=recorder.transcript_tail(session.call_id),
        )
        for session in runtime.active_sessions()
    ]
    return ActiveCallListResponse(calls=calls, count=len(calls))


# ---------------------------------------------------------------------- riwayat


@router.get("/export")
async def export_calls(
    admin: AdminDep,
    db: DatabaseDep,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    user: int | None = Query(None),
    outcome: str | None = Query(None, max_length=32),
) -> StreamingResponse:
    """Ekspor riwayat ke CSV memakai filter yang sama dengan `/calls` (Q14).

    Mengekspor **seluruh** hasil filter (bukan hanya halaman aktif), dibatasi
    `EXPORT_LIMIT` baris agar tidak menghabiskan memori.
    """
    del admin
    filters = _filters(1, EXPORT_LIMIT, date_from, date_to, user, outcome)
    rows = await calls_for_export(db, filters, limit=EXPORT_LIMIT)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow([_export_value(row, column) for column in EXPORT_COLUMNS])

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{EXPORT_FILENAME}"'},
    )


def _export_value(row: models.CallRecord, column: str) -> Any:
    value = getattr(row, column)
    if isinstance(value, datetime):
        return _iso(value)
    return "" if value is None else value


@router.get("", response_model=CallListResponse)
async def list_call_history(
    admin: AdminDep,
    db: DatabaseDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    user: int | None = Query(None),
    outcome: str | None = Query(None, max_length=32),
) -> CallListResponse:
    """Riwayat panggilan terpaginasikan dengan filter."""
    del admin
    result = await list_calls(db, _filters(page, page_size, date_from, date_to, user, outcome))
    total_pages = math.ceil(result.total / result.page_size) if result.total else 0
    return CallListResponse(
        items=[_summary(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=total_pages,
    )


# ------------------------------------------------------------------------- detail


@router.get("/{record_id}", response_model=CallDetail)
async def call_detail(
    admin: AdminDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    record_id: int,
) -> CallDetail:
    """Detail satu panggilan beserta jumlah transkrip & tool call."""
    del admin
    row = await _require_call(db, record_id)
    return CallDetail(
        **_summary(row).model_dump(),
        active=_find_session(runtime, row) is not None,
    )


@router.get("/{record_id}/transcript", response_model=TranscriptListResponse)
async def call_transcript(admin: AdminDep, db: DatabaseDep, record_id: int) -> TranscriptListResponse:
    """Transkrip satu panggilan, urut waktu (lama ke baru)."""
    del admin
    await _require_call(db, record_id)
    rows = await list_transcripts(db, record_id)
    return TranscriptListResponse(
        items=[
            TranscriptItem(id=row.id, speaker=row.speaker, text=row.text, at=row.at)
            for row in rows
        ],
        total=len(rows),
    )


@router.get("/{record_id}/tools", response_model=ToolCallListResponse)
async def call_tool_calls(admin: AdminDep, db: DatabaseDep, record_id: int) -> ToolCallListResponse:
    """Riwayat tool call satu panggilan, urut waktu."""
    del admin
    await _require_call(db, record_id)
    rows = await list_tool_calls(db, record_id)
    return ToolCallListResponse(
        items=[
            ToolCallItem(
                id=row.id,
                name=row.name,
                args=_decode(row.args_json),
                result=_decode(row.result_json),
                status=row.status,
                duration_ms=row.duration_ms,
                at=row.at,
            )
            for row in rows
        ],
        total=len(rows),
    )


# -------------------------------------------------------------------------- hangup


@router.post("/{record_id}/hangup", response_model=SimpleOkResponse)
async def hangup_call(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    request: Request,
    record_id: int,
) -> SimpleOkResponse:
    """Akhiri panggilan yang sedang berjalan.

    Menolak `404` bila record tidak ada atau panggilan sudah selesai. Aksi ini
    selalu dicatat di audit — sukses maupun gagal.
    """
    ip = _client_ip(request)
    row = await get_call(db, record_id)
    if row is None:
        await _audit_hangup(
            db, admin.username, {"record_id": record_id}, {"error": "call_not_found"}, ip
        )
        raise APIError(404, "call_not_found", "Panggilan tidak ditemukan.")

    session = _find_session(runtime, row)
    if session is None:
        await _audit_hangup(
            db,
            admin.username,
            {"record_id": record_id, "outcome": row.outcome},
            {"error": "call_not_active"},
            ip,
        )
        raise APIError(404, "call_not_active", "Panggilan tidak sedang aktif.")

    # `schedule_hangup` sinkron & idempoten: menunggu audio pamitan selesai.
    session.schedule_hangup(reason=END_REASON_PANEL)
    await _audit_hangup(
        db,
        admin.username,
        {"record_id": record_id, "tg_call_id": row.tg_call_id},
        {"requested": True},
        ip,
    )
    return SimpleOkResponse(ok=True)


async def _audit_hangup(
    db: DatabaseDep, actor: str, before: Any, after: Any, ip: str | None
) -> None:
    await record_audit(
        db,
        AuditEntry(
            action="call.hangup",
            actor=actor,
            target=AUDIT_TARGET,
            before=before,
            after=after,
            ip=ip,
        ),
    )