"""Tes regresi untuk temuan review Fase 2 (tiket D1/D2).

Setiap pengujian di sini mengunci satu perilaku yang sebelumnya salah; bila ada
yang kembali rusak, pengujian inilah yang pertama gagal.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from web_helpers import FakeTelegram, FakeTelegramClient, csrf_of, do_setup

from telegent.web.db import models
from telegent.web.db.base import Database, utcnow
from telegent.web.settings_store import SettingsStore
from telegent.web.telegram_errors import TelegramLoginError, map_exception
from telegent.web.telegram_login import TelegramCredentials, TelegramLoginService
from telegent.web.telegram_store import ACCOUNT_LOGGED_IN

_API_ID = 12345678
_API_HASH = "0123456789abcdef0123456789abcdef"
_PHONE = "+6281234567890"
_CODE = "54321"


@pytest.fixture
async def service(
    database: Database, store: SettingsStore, tmp_path: Path
) -> TelegramLoginService:
    await store.update({"telegram_api_id": _API_ID, "telegram_api_hash": _API_HASH})
    return TelegramLoginService(
        database,
        store,
        data_dir=tmp_path / "data",
        client_factory=FakeTelegram.factory,
    )


# ------------------------------------------------- [_BUG] _complete_login


async def test_login_tetap_berhasil_walau_get_me_gagal(
    service: TelegramLoginService, database: Database
) -> None:
    """`get_me()` gagal tidak boleh meninggalkan alur menggantung.

    Pyrogram sudah menulis berkas sesi saat otorisasi berhasil, jadi akun harus
    ditandai login dan baris `login_flow` tetap dibuang.
    """
    FakeTelegram.get_me_error = RuntimeError("profil tidak terjangkau")

    start = await service.start(_PHONE)
    result = await service.verify(start.flow_id, _CODE)
    assert result.next == "done"

    async with database.session() as session:
        account = await session.get(models.TelegramAccount, 1)
        assert account is not None
        assert account.status == ACCOUNT_LOGGED_IN
        assert account.tg_user_id is None  # profil kosong, status tetap benar

    from sqlalchemy import select

    async with database.session() as session:
        flows = (await session.execute(select(models.LoginFlow))).scalars().all()
    assert flows == [], "flow harus dibuang walau get_me gagal"


async def test_login_gagal_tetap_membuang_flow_bersama_sesi(
    service: TelegramLoginService, database: Database
) -> None:
    """Kegagalan `send_code` tidak menyisakan berkas sesi tanpa alur."""
    FakeTelegram.send_code_error = RuntimeError("tolak")

    with pytest.raises(TelegramLoginError):
        await service.start(_PHONE)

    from sqlalchemy import select

    async with database.session() as session:
        flows = (await session.execute(select(models.LoginFlow))).scalars().all()
    assert flows == []


# --------------------------------------------------------- [_BUG] lock I/O


async def test_ganti_akun_tidak_berhenti_karena_send_code_menggantung(
    service: TelegramLoginService,
) -> None:
    """Panggilan jaringan yang menggantung tidak boleh membekukan cancel/logout."""
    started = asyncio.Event()
    release = asyncio.Event()

    class HangingClient(FakeTelegramClient):  # type: ignore[name-defined,misc]
        async def send_code(self, phone: str) -> Any:
            started.set()
            await release.wait()  # simulasi jaringan menggantung
            return await super().send_code(phone)

    service._client_factory = lambda creds, workdir: HangingClient(creds, workdir)

    pending = asyncio.create_task(service.start(_PHONE))
    await asyncio.wait_for(started.wait(), timeout=1)

    # Operasi lain harus tetap merespons meski satu panggilan jaringan menggantung.
    cancel_task = asyncio.create_task(service.cleanup_expired())
    done, _ = await asyncio.wait({cancel_task}, timeout=1)
    assert done, "cleanup_expired tertahan oleh send_code yang menggantung"

    release.set()
    await asyncio.wait_for(pending, timeout=1)
    await cancel_task


# --------------------------------------------------- [_BUG] status read-only


async def test_status_tidak_menulis_database(
    service: TelegramLoginService, database: Database, tmp_path: Path
) -> None:
    """`GET /telegram/status` bersifat baca; status basi tak boleh diperbaiki diam-diam."""
    await service.start(_PHONE)
    # Buang berkas sesi supaya kondisi "perlu login ulang" terjadi.
    for path in (tmp_path / "data").glob("*.session*"):
        path.unlink()

    async with database.session() as session:
        row = await session.get(models.TelegramAccount, 1)
        assert row is not None
        row.status = ACCOUNT_LOGGED_IN
        row.session_name = "userbot_session"

    status = await service.status()
    assert status["status"] == "logged_out"  # diturunkan, bukan ditulis

    async with database.session() as session:
        row = await session.get(models.TelegramAccount, 1)
        assert row is not None
        assert row.status == ACCOUNT_LOGGED_IN, "GET tidak boleh menulis"


# ------------------------------------------- [_BUG] account_not_logged_in


async def test_logout_tanpa_login_menolak_dengan_kode_yang_tepat(
    service: TelegramLoginService,
) -> None:
    with pytest.raises(TelegramLoginError) as exc:
        await service.logout()
    assert exc.value.code == "account_not_logged_in"
    assert exc.value.status_code == 409


async def test_logout_tetap_boleh_bila_berkas_sesi_ada(
    service: TelegramLoginService, tmp_path: Path
) -> None:
    """Sesi di disk harus tetap bisa dibersihkan meski status belum `logged_in`."""
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "userbot_session.session").write_bytes(b"x")

    result = await service.logout()
    assert result["removed_session_files"] == 1


# ------------------------------------------------- [_BUG] kode network_error


def test_galat_jaringan_pakai_kode_terpisah() -> None:
    """`network_error` milik API generik; galat Telegram tak boleh memakai kode itu."""
    error = map_exception(ConnectionResetError("jputus"))
    assert error.code == "telegram_unreachable"
    assert error.code != "network_error"
    assert error.status_code == 502


# -------------------------------------------- AUTOINCREMENT selaras model


async def test_metadata_model_sama_dengan_hasil_migrasi(database: Database) -> None:
    """`create_all` harus menghasilkan AUTOINCREMENT, sama seperti migrasi."""
    from sqlalchemy import inspect

    async with database.engine.connect() as conn:
        ddl = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("login_flow")
        )
    # Kalau kolom `id` tidak AUTOINCREMENT, SQLite bisa memakai ulang rowid.
    async with database.engine.connect() as conn:
        raw = (await conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='login_flow'")).scalar_one()
    assert "AUTOINCREMENT" in raw.upper(), f"DDL tidak memakai AUTOINCREMENT: {raw}"
    assert ddl[0]["name"] == "id"


# ---------------------------------------------------- kredensial satu tipe


def test_kredensial_membawa_tiga_nilai_tanpa_bisa_tertukar() -> None:
    credentials = TelegramCredentials(api_id=1, api_hash="h", session_name="s")
    assert credentials.ready is True
    assert TelegramCredentials(api_id=0, api_hash="", session_name="s").ready is False
    # Nama field eksplisit mencegah tertukar saat diteruskan ke pabrik klien.
    assert set(vars(credentials)) == {"api_id", "api_hash", "session_name"}


# ------------------------------------------------------------- API-level


def test_endpoint_logout_menolak_belum_login(live_client: TestClient) -> None:
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}

    resp = live_client.post("/api/telegram/logout", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "account_not_logged_in"


def test_endpoint_status_tetap_read_only(live_client: TestClient) -> None:
    do_setup(live_client)
    # Dua pembacaan berturut-turut harus konsisten (tidak saling memperbaiki).
    first = live_client.get("/api/telegram/status").json()
    second = live_client.get("/api/telegram/status").json()
    assert first == second