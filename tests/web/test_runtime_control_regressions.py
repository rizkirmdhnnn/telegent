"""Tes regresi untuk temuan review Fase 4 (tiket F1/F3).

Men kunci lima perilaku yang sebelumnya salah: drain di luar lock, status yang tetap
RUNNING selama drain, retensi transkrip yang tidak pernah menghapus apa pun,
`drain_timeout` yang tidak bisa di-override, dan event status ganda.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from telegent.config import Settings
from telegent.web import retention_store
from telegent.web.call_store import add_transcript, start_call
from telegent.web.db.base import Database, utcnow
from telegent.web.runtime import RuntimeController, RuntimeState

_CREDENTIALS = {
    "telegram_api_id": 1,
    "telegram_api_hash": "0" * 32,
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}


class _Session:
    """Sesi tiruan; `auto_close=False` menahan drain sampai batas waktu."""

    def __init__(self, user_id: int, owner: Any, *, auto_close: bool = True) -> None:
        self.user_id = user_id
        self.owner = owner
        self.auto_close = auto_close
        self.hangups: list[str] = []
        self.closed = False

    def schedule_hangup(self, min_wait: float = 0.0, *, reason: str) -> None:
        self.hangups.append(reason)
        if self.auto_close:
            self.owner.sessions.pop(self.user_id, None)

    async def close(self) -> None:
        self.closed = True


class _App:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sessions: dict[int, _Session] = {}
        self.stopped = False
        self._done = asyncio.Event()

    def active_sessions(self) -> list[_Session]:
        return list(self.sessions.values())

    def add_session(self, user_id: int, *, auto_close: bool = True) -> _Session:
        session = _Session(user_id, self, auto_close=auto_close)
        self.sessions[user_id] = session
        return session

    async def start(self) -> None: ...

    async def stop(self) -> None:
        self.stopped = True
        self._done.set()

    async def wait_stopped(self) -> None:
        await self._done.wait()

    async def shutdown(self) -> None:
        self.sessions.clear()

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings

    def status_payload(self) -> dict:
        return {"running": True, "active_calls": len(self.sessions), "model": "m",
                "logged_in_user": None}


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "userbot_session.session").write_bytes(b"x")
    return directory


def _controller(store, sessions_dir: Path, events: list, **kwargs) -> tuple[RuntimeController, list]:
    apps: list[_App] = []

    def factory(settings: Settings) -> _App:
        app = _App(settings)
        apps.append(app)
        return app

    controller = RuntimeController(
        store,
        app_factory=factory,  # type: ignore[arg-type]
        session_dir=sessions_dir,
        event_sink=lambda nama, payload: events.append((nama, payload)),
        **kwargs,
    )
    return controller, apps


async def _subcounts(db: Database, record_id: int) -> tuple[int, int]:
    """Jumlah (transkrip, tool call) yang tersisa untuk satu panggilan."""
    from sqlalchemy import func, select

    from telegent.web.db import models

    async with db.session() as session:
        transkrip = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(models.TranscriptEntry)
                    .where(models.TranscriptEntry.call_record_id == record_id)
                )
            ).scalar_one()
        )
        tools = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(models.ToolCallRecord)
                    .where(models.ToolCallRecord.call_record_id == record_id)
                )
            ).scalar_one()
        )
    return transkrip, tools


async def _record(db: Database, record_id: int):
    from telegent.web.db import models

    async with db.session() as session:
        return await session.get(models.CallRecord, record_id)


# ------------------------------------------ [_BUG] drain di luar lock


async def test_start_tidak_bisa_masuk_saat_drain_berlangsung(
    store, sessions_dir: Path
) -> None:
    """`start()` harus terblokir sampai `stop()` selesai, bukan mematikan bot baru."""
    await store.update(_CREDENTIALS)
    events: list[tuple[str, dict]] = []
    controller, apps = _controller(store, sessions_dir, events, drain_timeout=0.5)

    await controller.start()
    # Sesi menolak tutup sendiri, sehingga drain benar-benar berjalan
    # sampai `drain_timeout` — ruang waktu yang harus dilindungi lock.
    apps[0].add_session(99, auto_close=False)

    stopping = asyncio.create_task(controller.stop())
    await asyncio.sleep(0.02)

    starting = asyncio.create_task(controller.start())
    await asyncio.sleep(0.02)
    assert not starting.done(), "`start()` masuk di tengah drain `stop()`"

    await stopping
    await asyncio.wait_for(starting, timeout=2)
    # Setelah semuanya selesai, bot boleh hidup lagi.
    assert controller.state is RuntimeState.RUNNING


# --------------------------------- [_BUG] status RUNNING selama drain


async def test_status_beralih_ke_stopping_sebelum_drain(store, sessions_dir: Path) -> None:
    await store.update(_CREDENTIALS)
    events: list[tuple[str, dict]] = []
    controller, apps = _controller(store, sessions_dir, events, drain_timeout=0.3)

    await controller.start()
    apps[0].add_session(99)
    events.clear()

    await controller.stop()

    status_during = [
        payload for nama, payload in events if nama == "status"
    ]
    assert status_during, "tidak ada event status saat stop"
    # Perubahan pertama harus sudah STOPPING, bukan RUNNING.
    assert status_during[0]["state"] == "stopping"


# -------------------------------------------- [_BUG] status terbit dobel


async def test_status_tidak_terbit_ganda_saat_stop(store, sessions_dir: Path) -> None:
    await store.update(_CREDENTIALS)
    events: list[tuple[str, dict]] = []
    controller, apps = _controller(store, sessions_dir, events, drain_timeout=0.5)

    await controller.start()
    events.clear()
    await controller.stop()

    status = [payload for nama, payload in events if nama == "status"]
    # Dua status itu wajar (stopping lalu stopped); yang dilarang duplikat identik.
    assert [payload["state"] for payload in status] == ["stopping", "stopped"]
    assert status[0] != status[1]


# ----------------------------------------- last_drained terekspos di status


async def test_last_drained_terekspos_di_status(store, sessions_dir: Path) -> None:
    await store.update(_CREDENTIALS)
    controller, apps = _controller(store, sessions_dir, [], drain_timeout=0.5)

    await controller.start()
    apps[0].add_session(99)
    await controller.stop()

    assert controller.status().last_drained == 1
    assert controller.status().to_dict()["last_drained"] == 1


# ------------------------------ [_BUG] retensi transkrip tidak pernah jalan


async def test_transkrip_lama_terhapus_walau_panggilan_disimpan(database: Database) -> None:
    """`transcripts_retention_days` harus bekerja meski panggilan disimpan selamanya."""
    lama = utcnow() - timedelta(days=90)
    record_id = await start_call(database, tg_call_id=1, user_id=1, started_at=lama)
    await add_transcript(database, record_id, speaker="caller", text="lama", at=lama)
    await add_transcript(database, record_id, speaker="caller", text="baru")

    policy = retention_store.RetentionPolicy(
        calls_days=0,  # panggilan disimpan selamanya
        transcripts_days=30,
        store_transcripts=True,
    )
    hasil = await retention_store.cleanup(database, policy)

    assert hasil.transcripts == 1, "transkrip lama tidak terhapus"
    assert hasil.calls == 0, "panggilan ikut terhapus padahal retensinya 0"

    transkrip_sisa, _ = await _subcounts(database, record_id)
    assert transkrip_sisa == 1, "transkrip yang baru ikut terhapus"


async def test_transcript_count_dikoreksi_setelah_pembersihan(database: Database) -> None:
    lama = utcnow() - timedelta(days=90)
    record_id = await start_call(database, tg_call_id=2, user_id=1, started_at=lama)
    for _ in range(3):
        await add_transcript(database, record_id, speaker="caller", text="lama", at=lama)

    await retention_store.cleanup(
        database,
        retention_store.RetentionPolicy(
            calls_days=0, transcripts_days=30, store_transcripts=True
        ),
    )

    transkrip_sisa, _ = await _subcounts(database, record_id)
    assert transkrip_sisa == 0
    detail = await _record(database, record_id)
    assert detail is not None
    assert detail.transcript_count == 0, "transcript_count tidak dikoreksi"


# ------------------------------------ audit_log tak pernah ikut terhapus


async def test_audit_log_tidak_ikut_terhapus(database: Database) -> None:
    from telegent.web.audit import AuditEntry, record_audit

    await record_audit(database, AuditEntry(action="uji", actor="admin", target="x"))
    await retention_store.cleanup(
        database,
        retention_store.RetentionPolicy(
            calls_days=0, transcripts_days=0, store_transcripts=True
        ),
    )
    from sqlalchemy import func, select

    from telegent.web.db import models

    async with database.session() as session:
        jumlah = int(
            (
                await session.execute(
                    select(func.count()).select_from(models.AuditLog)
                )
            ).scalar_one()
        )
    assert jumlah == 1, "audit_log ikut terhapus"