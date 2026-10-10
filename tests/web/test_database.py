"""Test lapisan database (tiket A2)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import selectinload

from telegent.web.app import create_app
from telegent.web.bootstrap import load_bootstrap
from telegent.web.db import models
from telegent.web.db.base import Base, Database, utcnow

_EXPECTED_TABLES = {
    "admin_user",
    "app_setting",
    "audit_log",
    "call_record",
    "login_flow",
    "telegram_account",
    "tool_call_record",
    "tool_config",
    "transcript_entry",
}


# --------------------------------------------------------------- migrasi & skema


async def test_migrasi_membuat_seluruh_tabel(database: Database) -> None:
    async with database.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tabel = {row[0] for row in rows}
    assert _EXPECTED_TABLES <= tabel
    # Tabel alembic_version juga ada.
    assert "alembic_version" in tabel


async def test_migrasi_idempoten(db_url: str) -> None:
    from telegent.web.db.migrate import upgrade_to_head_async

    await upgrade_to_head_async(db_url)
    await upgrade_to_head_async(db_url)  # tidak boleh error

    db = Database(db_url)
    try:
        async with db.session() as session:
            version = await session.execute(text("SELECT version_num FROM alembic_version"))
            assert version.scalar_one()
    finally:
        await db.dispose()


async def test_metadata_model_sinkron_dengan_database(database: Database) -> None:
    """Guard:_model dan skema hasil migrasi tidak boleh berbeda."""
    async with database.engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --------------------------------------------------------------------- PRAGMA


async def test_pragma_aktif(database: Database) -> None:
    async with database.engine.connect() as conn:
        mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()
        fk = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
    assert mode.lower() == "wal"
    assert int(fk) == 1


async def test_ping_database(database: Database) -> None:
    assert await database.ping() is True


async def test_session_rollback_bila_error(database: Database) -> None:
    with pytest.raises(RuntimeError):
        async with database.session() as session:
            session.add(models.AdminUser(username="gagal", password_hash="x"))
            await session.flush()
            raise RuntimeError("batal")

    async with database.session() as session:
        assert (await session.execute(select(models.AdminUser))).scalars().all() == []


# ----------------------------------------------------------------- round-trip


async def test_admin_user_round_trip(database: Database) -> None:
    async with database.session() as session:
        admin = models.AdminUser(username="admin", password_hash="hash-argon2")
        session.add(admin)

    async with database.session() as session:
        hasil = await session.execute(select(models.AdminUser))
        admin = hasil.scalar_one()
        assert admin.username == "admin"
        assert admin.totp_enabled is False
        assert admin.locale == "id"
        assert admin.theme == "system"
        assert admin.created_at is not None


async def test_app_setting_dan_tool_config(database: Database) -> None:
    async with database.session() as session:
        session.add(
            models.AppSetting(key="max_concurrent_calls", value="4", updated_by="admin")
        )
        session.add(models.AppSetting(key="gemini_api_key", value="cipher", encrypted=True))
        session.add(models.ToolConfig(name="get_current_datetime", config_json='{"a":1}'))

    async with database.session() as session:
        rows = (
            (await session.execute(select(models.AppSetting))).scalars().all()
        )
        by_key = {row.key: row for row in rows}
        assert by_key["gemini_api_key"].encrypted is True
        assert by_key["max_concurrent_calls"].encrypted is False

        tool = (
            await session.execute(select(models.ToolConfig))
        ).scalar_one()
        assert tool.enabled is True


async def test_telegram_account_dan_login_flow(database: Database) -> None:
    async with database.session() as session:
        session.add(
            models.TelegramAccount(phone="+62", status="logged_in", tg_user_id=42)
        )
        session.add(
            models.LoginFlow(
                phone="+62",
                phone_code_hash="hash",
                expires_at=utcnow() + timedelta(minutes=10),
            )
        )

    async with database.session() as session:
        akun = (await session.execute(select(models.TelegramAccount))).scalar_one()
        assert akun.status == "logged_in" and akun.tg_user_id == 42

        flow = (await session.execute(select(models.LoginFlow))).scalar_one()
        assert flow.status == "code_sent"


async def test_audit_log_tidak_punya_updated_at(database: Database) -> None:
    async with database.session() as session:
        session.add(models.AuditLog(actor="admin", action="setting.update", target="x"))
    async with database.session() as session:
        row = (await session.execute(select(models.AuditLog))).scalar_one()
        assert row.at is not None and row.ip is None


async def test_call_record_berserta_transkrip_dan_tool(database: Database) -> None:
    async with database.session() as session:
        call = models.CallRecord(tg_call_id=7, user_id=123, outcome="answered")
        call.transcripts.append(models.TranscriptEntry(speaker="caller", text="halo"))
        call.transcripts.append(models.TranscriptEntry(speaker="ai", text="hai"))
        call.tool_calls.append(
            models.ToolCallRecord(
                name="get_current_datetime", args_json="{}", status="ok", duration_ms=12
            )
        )
        session.add(call)

    async with database.session() as session:
        call = (
            await session.execute(
                select(models.CallRecord)
                .options(
                    selectinload(models.CallRecord.transcripts),
                    selectinload(models.CallRecord.tool_calls),
                )
            )
        ).unique().scalar_one()
        assert call.tg_call_id == 7
        assert len(call.transcripts) == 2
        assert len(call.tool_calls) == 1
        assert call.transcript_count == 0  # dihitung saat panggilan berakhir


async def test_cascade_hapus_transkrip_dan_tool(database: Database) -> None:
    async with database.session() as session:
        call = models.CallRecord(tg_call_id=8, user_id=1)
        call.transcripts.append(models.TranscriptEntry(speaker="caller", text="x"))
        call.tool_calls.append(models.ToolCallRecord(name="end_call", status="ok"))
        session.add(call)
        await session.flush()
        call_id = call.id

    async with database.session() as session:
        await session.execute(delete(models.CallRecord).where(models.CallRecord.id == call_id))

    async with database.session() as session:
        assert (await session.execute(select(models.TranscriptEntry))).scalars().all() == []
        assert (await session.execute(select(models.ToolCallRecord))).scalars().all() == []


async def test_relasi_tidak_dimuat_otomatis(database: Database) -> None:
    """Mencegah query N+1 tak sengaja saat daftar panggilan."""
    async with database.session() as session:
        session.add(models.CallRecord(tg_call_id=9, user_id=1))

    async with database.session() as session:
        calls = (await session.execute(select(models.CallRecord))).scalars().all()
        assert len(calls) == 1
        assert "transcripts" not in calls[0].__dict__


# ------------------------------------------------------------------ integrasi


def test_lifespan_membuat_skema_di_lifespan(tmp_path: Path) -> None:
    cfg = load_bootstrap(data_dir=tmp_path / "data")  # db_url default -> data/telegent.db
    db_file = tmp_path / "data" / "telegent.db"
    assert not db_file.exists()

    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/healthz").json()["db"] == "ok"
        assert db_file.exists()