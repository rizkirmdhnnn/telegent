"""Test audit log (tiket A6)."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from web_helpers import do_setup, login
from sqlalchemy import select

from telegent.web.audit import (
    AuditEntry,
    is_secret_key,
    record_audit,
    record_many,
    sanitize,
)
from telegent.web.bootstrap import BootstrapConfig
from telegent.web.db import models
from telegent.web.db.base import Database
from telegent.web.settings_store import SettingsStore

_CREDENTIALS = {
    "telegram_api_id": 12345678,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}


async def _entries(database: Database) -> list[models.AuditLog]:
    async with database.session() as session:
        return list((await session.execute(select(models.AuditLog))).scalars().all())


# ---------------------------------------------------------------- sanitasi


def test_is_secret_key_mengenali_pola() -> None:
    assert is_secret_key("gemini_api_key") is True
    assert is_secret_key("telegram_api_hash") is True
    assert is_secret_key("password") is True
    assert is_secret_key("csrf_token") is True
    assert is_secret_key("max_concurrent_calls") is False
    assert is_secret_key("system_instruction") is False


def test_sanitize_menyamarkan_nilai_secret_nested() -> None:
    data = {
        "gemini_api_key": "AIzaSy0123456789012345678901234567890",
        "nested": {"password": "rahasia", "max_concurrent_calls": 4},
        "list": [{"api_key": "abc"}],
    }
    hasil = sanitize(data)

    assert "AIzaSy0123456789" not in json.dumps(hasil)
    assert hasil["nested"]["max_concurrent_calls"] == 4
    assert hasil["nested"]["password"] != "rahasia"
    assert hasil["list"][0]["api_key"] != "abc"


def test_sanitize_menjaga_tipe_sederhana() -> None:
    assert sanitize({"a": 1, "b": True, "c": None}) == {"a": 1, "b": True, "c": None}
    assert sanitize("teks") == "teks"


def test_sanitize_membatasi_kedalaman() -> None:
    dalam: dict = {"x": 1}
    for _ in range(10):
        dalam = {"child": dalam}
    assert "…" in str(sanitize(dalam))


# --------------------------------------------------------------- penulisan


async def test_record_audit_menyimpan_entri(database: Database) -> None:
    await record_audit(
        database, AuditEntry(action="runtime.restart", actor="admin", target="bot")
    )
    rows = await _entries(database)
    assert len(rows) == 1
    assert rows[0].action == "runtime.restart"
    assert rows[0].actor == "admin"


async def test_record_audit_menyamarkan_nilai_secret(database: Database) -> None:
    await record_audit(
        database,
        AuditEntry(
            action="credential.update",
            actor="admin",
            target="gemini_api_key",
            before="AIzaLama0123456789012345",
            after="AIzaBaru0123456789012345",
        ),
    )
    row = (await _entries(database))[0]
    assert "AIzaBaru" not in (row.after_json or "")
    assert "AIzaLama" not in (row.before_json or "")
    assert json.loads(row.after_json or "null") is not None


async def test_record_audit_gagal_tidak_melempar(monkeypatch, database: Database) -> None:
    """Kegagalan audit tidak boleh menggagalkan aksi utama."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("db mati")

    monkeypatch.setattr(database, "session", boom)
    await record_audit(database, AuditEntry(action="x"))  # tidak melempar


# --------------------------------------------------- integrasi settings store


async def test_perubahan_setting_mencatat_audit(
    database: Database, store: SettingsStore
) -> None:
    await store.update({**_CREDENTIALS, "max_concurrent_calls": 5}, actor="admin", ip="10.0.0.5")

    rows = await _entries(database)
    actions = {row.target for row in rows}
    assert actions == set(_CREDENTIALS) | {"max_concurrent_calls"}
    assert all(row.action == "setting.update" for row in rows)
    assert all(row.actor == "admin" and row.ip == "10.0.0.5" for row in rows)

    perubahan = next(row for row in rows if row.target == "max_concurrent_calls")
    assert json.loads(perubahan.before_json or "null") == 4
    assert json.loads(perubahan.after_json or "null") == 5


async def test_reset_default_tercatat(database: Database, store: SettingsStore) -> None:
    await store.update({"max_concurrent_calls": 9}, actor="admin")
    await store.reset_to_default(["max_concurrent_calls"], actor="admin")
    # reset_to_default belum mencatat audit (dicatat oleh router pada tiket C1),
    # tetapi perubahan awal harus tercatat.
    assert any(row.target == "max_concurrent_calls" for row in await _entries(database))


# ------------------------------------------------------------------- endpoint


def _write_audit(db_url: str, entries: list[AuditEntry]) -> None:
    """Tulis entri audit dari luar loop aplikasi (engine terpisah, DB sama)."""

    async def run() -> None:
        db = Database(db_url)
        try:
            await record_many(db, entries)
        finally:
            await db.dispose()

    asyncio.run(run())


def test_endpoint_audit_menolak_tanpa_sesi(live_client: TestClient) -> None:
    assert live_client.get("/api/audit").status_code == 401


def test_endpoint_audit_menampilkan_entri(
    live_client: TestClient, bootstrap: BootstrapConfig
) -> None:
    do_setup(live_client)
    login(live_client)
    _write_audit(
        bootstrap.db_url,
        [
            AuditEntry(
                action="runtime.start", actor="admin", target="bot", after={"ok": True}
            )
        ],
    )

    resp = live_client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["items"][0]["action"] == "runtime.start"
    assert body["items"][0]["at"].endswith("Z")
    assert body["items"][0]["after"] == {"ok": True}


def test_endpoint_audit_filter_dan_paginasi(
    live_client: TestClient, bootstrap: BootstrapConfig
) -> None:
    do_setup(live_client)
    login(live_client)
    _write_audit(
        bootstrap.db_url,
        [AuditEntry(action="a.jalan", actor="admin", target=f"t{i}") for i in range(7)]
        + [AuditEntry(action="b.lain", actor="admin")],
    )

    semua = live_client.get("/api/audit", params={"page_size": 100}).json()
    assert semua["total"] == 8

    halaman = live_client.get("/api/audit", params={"page": 2, "page_size": 5}).json()
    assert len(halaman["items"]) == 3
    assert halaman["page"] == 2

    difilter = live_client.get("/api/audit", params={"action": "b.lain"}).json()
    assert difilter["total"] == 1

    aksi = live_client.get("/api/audit/actions").json()
    assert aksi["actions"] == ["a.jalan", "b.lain"]