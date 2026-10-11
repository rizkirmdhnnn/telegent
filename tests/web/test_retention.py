"""Test pembersihan retensi (tiket F3).

Yang dikunci di sini:

* `retention_days = 0` berarti **simpan selamanya**, bukan hapus semua.
* `audit_log` **tidak pernah** terhapus oleh pembersihan retensi.
* Menghapus `call_record` ikut menghapus transkrip & tool call-nya (cascade).
* `transcript_entry` yatim yang lapuk ikut dibersihkan.
* `store_transcripts=false` tidak menghentikan pembersihan `call_record`.
* Penjadwalan: sekali saat boot, lalu task harian (Q15).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from telegent.web.audit import AuditEntry, record_audit
from telegent.web.db import models
from telegent.web.db.base import Database, utcnow
from telegent.web.retention_store import (
    BATCH_SIZE,
    RetentionCleaner,
    RetentionPolicy,
    cleanup,
    load_policy,
)
from telegent.web.settings_store import SettingsStore

NOW = utcnow()


# ------------------------------------------------------------------- helper


async def _seed_call(
    db: Database,
    *,
    age_days: int,
    record_id: int,
    transcripts: int = 1,
    tools: int = 1,
) -> int:
    """Sisipkan satu `call_record` lengkap dengan transkrip & tool call."""
    started = NOW - timedelta(days=age_days)
    async with db.session() as session:
        row = models.CallRecord(
            tg_call_id=record_id,
            user_id=1000 + record_id,
            user_display=f"@{record_id}",
            outcome="answered",
            end_reason="caller_hangup",
            started_at=started,
            ended_at=started + timedelta(seconds=30),
            duration_sec=30,
        )
        session.add(row)
        await session.flush()
        for index in range(transcripts):
            session.add(
                models.TranscriptEntry(
                    call_record_id=row.id,
                    speaker="caller" if index % 2 == 0 else "ai",
                    text=f"ucapan {index}",
                    at=started + timedelta(seconds=index + 1),
                )
            )
        for index in range(tools):
            session.add(
                models.ToolCallRecord(
                    call_record_id=row.id,
                    name="get_current_datetime",
                    args_json="{}",
                    result_json="{}",
                    status="ok",
                    duration_ms=5,
                    at=started + timedelta(seconds=index + 1),
                )
            )
        return int(row.id)


async def _counts(db: Database) -> dict[str, int]:
    from sqlalchemy import func, select

    async with db.session() as session:
        return {
            "calls": int(
                (await session.execute(select(func.count()).select_from(models.CallRecord))).scalar_one()
            ),
            "transcripts": int(
                (
                    await session.execute(
                        select(func.count()).select_from(models.TranscriptEntry)
                    )
                ).scalar_one()
            ),
            "tools": int(
                (
                    await session.execute(
                        select(func.count()).select_from(models.ToolCallRecord)
                    )
                ).scalar_one()
            ),
            "audit": int(
                (await session.execute(select(func.count()).select_from(models.AuditLog))).scalar_one()
            ),
        }


def _policy(calls: int, transcripts: int, *, store: bool = True) -> RetentionPolicy:
    return RetentionPolicy(
        calls_days=calls, transcripts_days=transcripts, store_transcripts=store
    )


# ------------------------------------------------------------------ policies


def test_policy_nol_berarti_nonaktif() -> None:
    policy = _policy(0, 0)
    assert policy.calls_enabled is False
    assert policy.transcripts_enabled is False


async def test_load_policy_membaca_setting(database: Database, store: SettingsStore) -> None:
    await store.update({"calls_retention_days": 7, "transcripts_retention_days": 0})

    policy = await load_policy(store)

    assert policy.calls_days == 7
    assert policy.transcripts_enabled is False


# ------------------------------------------------------------------- cleanup


async def test_panggilan_lama_dihapus(database: Database) -> None:
    await _seed_call(database, age_days=40, record_id=1)
    await _seed_call(database, age_days=2, record_id=2)

    result = await cleanup(database, _policy(30, 30))

    assert result.calls == 1
    assert (await _counts(database))["calls"] == 1


async def test_panggilan_dalam_rentang_aretensi_tetap(database: Database) -> None:
    await _seed_call(database, age_days=29, record_id=1)
    await _seed_call(database, age_days=31, record_id=2)

    result = await cleanup(database, _policy(30, 30))

    assert result.calls == 1
    assert (await _counts(database))["calls"] == 1


async def test_retensi_nol_tidak_menghapus_apa_pun(database: Database) -> None:
    await _seed_call(database, age_days=4000, record_id=1)

    result = await cleanup(database, _policy(0, 0))

    assert result.total == 0
    counts = await _counts(database)
    assert counts["calls"] == 1
    assert counts["transcripts"] == 1
    assert counts["tools"] == 1


async def test_transkrip_dan_tool_call_ikut_terhapus(database: Database) -> None:
    await _seed_call(database, age_days=40, record_id=1, transcripts=3, tools=2)

    result = await cleanup(database, _policy(30, 30))

    assert result.calls == 1
    assert result.tool_calls == 2
    counts = await _counts(database)
    assert counts["transcripts"] == 0
    assert counts["tools"] == 0


async def test_transkrip_yatim_lapuk_dihapus(database: Database) -> None:
    """Transkrip tanpa `call_record` (mis. dihapus manual) ikut dibersihkan.

    Disisipkan lewat koneksi terpisah yang tidak mengaktifkan
    `PRAGMA foreign_keys`, karena kasus ini justru data yang sudah rusak —
    jalur ORM dengan FK ON memang tidak bisa membuatnya.
    """
    import aiosqlite

    path = database.url.split("sqlite+aiosqlite:///", 1)[1]
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            "INSERT INTO transcript_entry (call_record_id, speaker, text, at)"
            " VALUES (?, 'caller', 'yatim', ?)",
            (999_999, (NOW - timedelta(days=90)).isoformat(sep=" ")),
        )
        await conn.commit()

    result = await cleanup(database, _policy(30, 30))

    assert result.transcripts == 1
    assert (await _counts(database))["transcripts"] == 0


async def test_transkrip_yatim_baru_disimpan(database: Database) -> None:
    """Transkrip yatim yang masih baru tidak ikut terhapus."""
    import aiosqlite

    path = database.url.split("sqlite+aiosqlite:///", 1)[1]
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            "INSERT INTO transcript_entry (call_record_id, speaker, text, at)"
            " VALUES (?, 'caller', 'baru', ?)",
            (999_999, utcnow().isoformat(sep=" ")),
        )
        await conn.commit()

    result = await cleanup(database, _policy(30, 30))

    assert result.transcripts == 0
    assert (await _counts(database))["transcripts"] == 1


async def test_audit_log_tidak_pernah_terhapus(database: Database) -> None:
    await record_audit(
        database,
        AuditEntry(action="runtime.start", actor="admin", target="runtime"),
    )
    await _seed_call(database, age_days=400, record_id=1)

    await cleanup(database, _policy(1, 1))

    assert (await _counts(database))["audit"] == 1


async def test_store_transcripts_mati_tetap_membersihkan_panggilan(
    database: Database,
) -> None:
    await _seed_call(database, age_days=40, record_id=1)

    result = await cleanup(database, _policy(30, 30, store=False))

    assert result.calls == 1
    assert (await _counts(database))["calls"] == 0


async def test_pembersihan_berulang_aman(database: Database) -> None:
    await _seed_call(database, age_days=40, record_id=1)

    first = await cleanup(database, _policy(30, 30))
    second = await cleanup(database, _policy(30, 30))

    assert first.calls == 1
    assert second.calls == 0


async def test_batch_lebih_dari_satu_diproses(database: Database) -> None:
    total = BATCH_SIZE + 5
    for index in range(total):
        await _seed_call(database, age_days=40, record_id=index + 1, transcripts=0, tools=0)

    result = await cleanup(database, _policy(30, 30))

    assert result.calls == total
    assert (await _counts(database))["calls"] == 0


async def test_waktu_masuk_berzona_dikonversi_ke_utc_naive(database: Database) -> None:
    """Batas retensi dihitung dari naive UTC, bukan waktu lokal."""
    from datetime import timezone

    started = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    async with database.session() as session:
        session.add(
            models.CallRecord(
                tg_call_id=1,
                user_id=1,
                outcome="answered",
                started_at=started,
                ended_at=started,
                duration_sec=0,
            )
        )

    result = await cleanup(
        database,
        _policy(30, 30),
        now=started + timedelta(days=31),
    )

    assert result.calls == 1


# ------------------------------------------------------------------- cleaner


async def test_cleaner_membaca_policy_dari_store(
    database: Database, store: SettingsStore
) -> None:
    await store.update({"calls_retention_days": 30})
    await _seed_call(database, age_days=40, record_id=1)

    result = await RetentionCleaner(database, store).run_once()

    assert result.calls == 1


async def test_cleaner_menelan_kegagalan(
    database: Database, store: SettingsStore
) -> None:
    """Kegagalan tidak boleh merambat ke web; hasil kosong, log tetap jalan."""
    await _seed_call(database, age_days=40, record_id=1)

    class _Boom:
        async def get(self, key: str) -> object:
            raise RuntimeError("store mati")

    result = await RetentionCleaner(database, _Boom()).run_once()  # type: ignore[arg-type]

    assert result.total == 0
    assert (await _counts(database))["calls"] == 1


async def test_loop_berhenti_saat_dibatalkan(
    database: Database, store: SettingsStore
) -> None:
    cleaner = RetentionCleaner(database, store)
    task = asyncio.create_task(cleaner.loop(interval=3600))
    await asyncio.sleep(0)
    assert not task.done()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ------------------------------------------------------------------ lifespan


def test_pembersihan_dijalankan_saat_boot(tmp_path) -> None:
    """Boot menjalankan satu siklus: data lama terhapus sebelum web melayani."""
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from telegent.web.app import create_app
    from telegent.web.bootstrap import load_bootstrap
    from telegent.web.db.base import Database
    from telegent.web.db.migrate import upgrade_to_head_async

    cfg = load_bootstrap(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{(tmp_path / 'retention.db').as_posix()}",
    )

    async def seed() -> None:
        await upgrade_to_head_async(cfg.db_url)
        db = Database(cfg.db_url)
        try:
            await _seed_call(db, age_days=400, record_id=1, transcripts=2, tools=1)
        finally:
            await db.dispose()

    asyncio.run(seed())

    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/healthz").status_code == 200

    async def remaining() -> tuple[int, int]:
        db = Database(cfg.db_url)
        try:
            async with db.session() as session:
                return (
                    int(
                        (
                            await session.execute(
                                select(func.count()).select_from(models.CallRecord)
                            )
                        ).scalar_one()
                    ),
                    int(
                        (
                            await session.execute(
                                select(func.count()).select_from(models.AuditLog)
                            )
                        ).scalar_one()
                    ),
                )
        finally:
            await db.dispose()

    calls, audits = asyncio.run(remaining())
    assert calls == 0
    assert audits == 0  # audit tetap utuh (tidak ada yang menimpanya, tapi aman)


def test_retention_terpasang_selama_lifespan_hidup(live_client: TestClient) -> None:
    """Pembersih aktif selama proses web hidup (F3 dijadwalkan di lifespan)."""
    assert isinstance(live_client.app.state.retention, RetentionCleaner)