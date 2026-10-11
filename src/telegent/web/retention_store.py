"""Pembersihan data lama sesuai kebijakan retensi (spesifikasi §4, §5).

Pola `*_store.py`: fungsi repo murni yang hanya menyentuh database, tanpa event
bus maupun task background. Penjadwalan (harian + sekali saat boot, Q15) tetap
diurus `RetentionCleaner` supaya modul ini mudah diuji tanpa event loop.

Aturan penting:

- Nilai retensi **0 berarti simpan selamanya** — bukan "hapus semua".
- `audit_log` **tidak pernah** dihapus: itu jejak administratif, bukan data
  operasional (spesifikasi §5.9).
- Penghapusan `call_record` bersifat cascade ke `transcript_entry` dan
  `tool_call_record` lewat `ON DELETE CASCADE` + `PRAGMA foreign_keys=ON`.
- Log hanya melaporkan **jumlah baris**, tanpa isi data.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult

from telegent.web.db import models
from telegent.web.db.base import Database, utcnow
from telegent.web.settings_store import SettingsStore

log = logging.getLogger("telegent.web.retention")

#: Kunci setting yang dipakai modul ini.
KEY_CALLS_RETENTION = "calls_retention_days"
KEY_TRANSCRIPTS_RETENTION = "transcripts_retention_days"
KEY_STORE_TRANSCRIPTS = "store_transcripts"

#: Jarak aman dari `now`: baris tepat pada batas retensi masih dipertahankan.
_EPSILON = timedelta(seconds=1)

#: Jumlah baris per batch (SQLite; menjaga transaksi pendek & lock singkat).
BATCH_SIZE = 500

#: Jadwal harian (Q15: harian saat boot, lalu setiap 24 jam).
DAILY_INTERVAL_SEC = 24 * 60 * 60


@dataclass(frozen=True)
class RetentionPolicy:
    """Nilai retensi yang berlaku saat satu siklus pembersihan."""

    calls_days: int
    transcripts_days: int
    store_transcripts: bool

    @property
    def calls_enabled(self) -> bool:
        return self.calls_days > 0

    @property
    def transcripts_enabled(self) -> bool:
        # `store_transcripts=false` berarti tidak ada transkrip baru yang
        # disimpan; sisa lama tetap perlu dibersihkan bila policy-nya menyala.
        return self.transcripts_days > 0


@dataclass(frozen=True)
class CleanupResult:
    """Jumlah baris yang terhapus per jenis (tanpa isi data)."""

    calls: int = 0
    transcripts: int = 0
    tool_calls: int = 0

    @property
    def total(self) -> int:
        return self.calls + self.transcripts + self.tool_calls

    def __add__(self, other: CleanupResult) -> CleanupResult:
        return CleanupResult(
            calls=self.calls + other.calls,
            transcripts=self.transcripts + other.transcripts,
            tool_calls=self.tool_calls + other.tool_calls,
        )


async def load_policy(store: SettingsStore) -> RetentionPolicy:
    """Baca kebijakan retensi terbaru dari store."""
    calls = await store.get(KEY_CALLS_RETENTION)
    transcripts = await store.get(KEY_TRANSCRIPTS_RETENTION)
    store_transcripts = await store.get(KEY_STORE_TRANSCRIPTS)
    return RetentionPolicy(
        calls_days=int(calls or 0),
        transcripts_days=int(transcripts or 0),
        store_transcripts=bool(store_transcripts),
    )


def cutoff(days: int, *, now: datetime | None = None) -> datetime:
    """Ambang waktu (naive UTC): baris sebelum ini dianggap kedaluwarsa."""
    base = now or utcnow()
    return base - timedelta(days=days) + _EPSILON


async def delete_old_calls(db: Database, before: datetime) -> tuple[int, int]:
    """Hapus `call_record` yang lebih tua dari `before`; ikut transkrip & tool call.

    Mengembalikan `(jumlah panggilan, jumlah tool call)` yang ikut terhapus
    lewat cascade. Transkrip ikut terhapus dengan baris induknya, sehingga tidak
    dihitung terpisah (baris*yatim* yang tersisa ditangani `delete_orphan_transcripts`).
    """
    calls = 0
    tool_calls = 0
    while True:
        async with db.session() as session:
            ids = list(
                (
                    await session.execute(
                        select(models.CallRecord.id)
                        .where(models.CallRecord.started_at < before)
                        .limit(BATCH_SIZE)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                return calls, tool_calls
            tool_calls += int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(models.ToolCallRecord)
                        .where(models.ToolCallRecord.call_record_id.in_(ids))
                    )
                ).scalar_one()
            )
            result = await session.execute(
                delete(models.CallRecord).where(models.CallRecord.id.in_(ids))
            )
        calls += int(cast("CursorResult[Any]", result).rowcount or 0)
        if len(ids) < BATCH_SIZE:
            return calls, tool_calls


async def delete_orphan_transcripts(db: Database, before: datetime) -> int:
    """Hapus `transcript_entry` yatim yang lebih tua dari `before`.

    "Yatim" berarti `call_record_id`-nya tidak lagi ada (mis.-record dihapus
    manual lewat SQL). Transkrip yang induknya masih ada ikut terhapus saat
    `call_record` dihapus, jadi jalur ini hanya untuk sisa-sisa.
    """
    total = 0
    while True:
        async with db.session() as session:
            ids = list(
                (
                    await session.execute(
                        select(models.TranscriptEntry.id)
                        .where(
                            models.TranscriptEntry.at < before,
                            models.TranscriptEntry.call_record_id.not_in(
                                select(models.CallRecord.id)
                            ),
                        )
                        .limit(BATCH_SIZE)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                return total
            result = await session.execute(
                delete(models.TranscriptEntry).where(models.TranscriptEntry.id.in_(ids))
            )
        total += int(cast("CursorResult[Any]", result).rowcount or 0)
        if len(ids) < BATCH_SIZE:
            return total


async def cleanup(db: Database, policy: RetentionPolicy, *, now: datetime | None = None) -> CleanupResult:
    """Jalankan satu siklus pembersihan; kembalikan jumlah baris terhapus."""
    result = CleanupResult()
    moment = now or utcnow()

    if policy.calls_enabled:
        calls, tools = await delete_old_calls(
            db, cutoff(policy.calls_days, now=moment)
        )
        result = result + CleanupResult(calls=calls, tool_calls=tools)

    if policy.transcripts_enabled:
        result = result + CleanupResult(
            transcripts=await delete_orphan_transcripts(
                db, cutoff(policy.transcripts_days, now=moment)
            )
        )

    if result.total:
        log.info(
            "Pembersihan retensi: %d panggilan, %d transkrip, %d tool call dihapus "
            "(retensi panggilan=%s hari, transkrip=%s hari).",
            result.calls,
            result.transcripts,
            result.tool_calls,
            policy.calls_days,
            policy.transcripts_days,
        )
    return result


class RetentionCleaner:
    """Menjalankan `cleanup` sesuai jadwal: sekali saat boot, lalu harian (Q15)."""

    def __init__(self, db: Database, store: SettingsStore) -> None:
        self._db = db
        self._store = store

    async def run_once(self) -> CleanupResult:
        """Satu siklus; kegagalan diisolasi agar penjadwalan terus berjalan."""
        try:
            policy = await load_policy(self._store)
            return await cleanup(self._db, policy)
        except Exception:
            log.exception("Gagal menjalankan pembersihan retensi.")
            return CleanupResult()

    async def loop(self, interval: float = DAILY_INTERVAL_SEC) -> None:
        """Bersihkan lalu tunggu `interval`, berulang sampai task dibatalkan."""
        while True:
            try:
                await asyncio.sleep(interval)
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Pembersihan retensi terjadwal gagal.")
                await asyncio.sleep(interval)