"""Test tambahan: event bus, pemetaan galat Telegram, migrasi sinkron, store.

Berisi cabang yang belum tersentuh oleh fase sebelumnya (lihat audit H1):
- `EventBus.subscribe(replay=…)`, `Subscription.aclose()` idempoten, serta
  penghitung pengikut/riwayat;
- pemetaan exception jaringan → `telegram_unreachable` (502);
- `dumps_json` sudah ada di `test_security_regressions`; di sini konfigurasi
  tool & setelan yang bermasalah harus ditangani tanpa 500.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from telegent.web.db.base import Database
from telegent.web.events import DEFAULT_HISTORY_SIZE, EventBus
from telegent.web.settings_store import SettingsStore
from telegent.web.telegram_errors import (
    DEFAULT_MESSAGES,
    TelegramLoginError,
    map_exception,
)


# -------------------------------------------------------------- EventBus


async def test_replay_mengembalikan_riwayat_terakhir() -> None:
    """Klien baru menerima event terakhir supaya UI langsung konsisten."""
    bus = EventBus()
    for i in range(5):
        bus.publish("status", {"i": i})

    sub = bus.subscribe(replay=2)

    assert [(await sub.__anext__()).data["i"] for _ in range(2)] == [3, 4]


async def test_replay_nol_tidak_mengembalikan_apa_pun() -> None:
    bus = EventBus()
    bus.publish("status", {})
    sub = bus.subscribe(replay=0)
    # Tidak ada antrean tertunda: pengikut hanya menunggu event baru.
    bus.publish("status", {"baru": True})
    assert (await sub.__anext__()).data == {"baru": True}


async def test_replay_dibatasi_ukuran_riwayat() -> None:
    """`replay` lebih besar dari riwayat tidak boleh resurrect event lama."""
    bus = EventBus(history_size=2)
    for i in range(10):
        bus.publish("status", {"i": i})

    sub = bus.subscribe(replay=99)

    assert [(await sub.__anext__()).data["i"] for _ in range(2)] == [8, 9]


async def test_riwayat_dibatasi_default() -> None:
    """Replay tidak boleh lebih panjang dari Maximum riwayat yang disimpan."""
    bus = EventBus(history_size=DEFAULT_HISTORY_SIZE)
    for i in range(DEFAULT_HISTORY_SIZE + 50):
        bus.publish("status", {"i": i})

    sub = bus.subscribe(replay=DEFAULT_HISTORY_SIZE)

    for _ in range(DEFAULT_HISTORY_SIZE):
        await sub.__anext__()
    # Event ke-(N+1) tidak ada di replay; pengikut hanya bisa menunggu yang baru.
    bus.publish("status", {"setelah_replay": True})
    assert (await asyncio.wait_for(sub.__anext__(), timeout=1)).data == {"setelah_replay": True}


def test_aclose_idempoten() -> None:
    bus = EventBus()
    sub = bus.subscribe()
    assert bus.subscriber_count == 1

    asyncio.run(sub.aclose())
    asyncio.run(sub.aclose())

    assert bus.subscriber_count == 0


def test_publish_setelah_unsubscribe_tidak_menahan() -> None:
    """Event untuk pengikut yang sudah menutup tidak boleh error."""
    bus = EventBus()
    sub = bus.subscribe()
    asyncio.run(sub.aclose())

    bus.publish("status", {"ok": True})  # tidak boleh melempar

    assert bus.subscriber_count == 0


def test_event_drop_terhitung_saat_pengikut_lambat() -> None:
    """Antrean penuh: event dibuang, pengikut **tidak** dilepas.

    Kalau pengikut lambat ikut di-*unsubscribe*, panel akan diam-diam berhenti
    menerima update tanpa ada yang tahu.
    """
    bus = EventBus(queue_size=2)
    bus.subscribe()
    for i in range(5):
        bus.publish("status", {"i": i})

    assert bus.dropped == 3  # 5 event, hanya 2 yang muat
    assert bus.subscriber_count == 1


def test_clear_history() -> None:
    bus = EventBus()
    bus.publish("status", {})
    bus.clear_history()
    sub = bus.subscribe(replay=5)
    assert not sub._replay  # tidak ada sisa riwayat setelah dihapus


# --------------------------------------------------- pemetaan galat Telegram


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionResetError(),
        TimeoutError(),
        OSError("koneksi refused"),
        TimeoutError("timeout"),
    ],
)
def test_galat_jaringan_menjadi_502(exc: BaseException) -> None:
    error = map_exception(exc)
    assert error.code == "telegram_unreachable"
    assert error.status_code == 502


def test_exception_tidak_dikenal_menjadi_502() -> None:
    error = map_exception(ValueError("aneh"))
    assert error.code == "telegram_error"
    assert error.status_code == 502


def test_semua_kode_ada_pesan_cadangan() -> None:
    """UI menerjemahkan lewat katalog; pesan cadangan adalah jaring pengaman."""
    error = TelegramLoginError("flood_wait")
    assert error.message == DEFAULT_MESSAGES["flood_wait"]


def test_kode_tanpa_pesan_cadangan_memakai_kodenya() -> None:
    assert TelegramLoginError("kode_baru").message == "kode_baru"


def test_fields_kosong_bila_tanpa_retry_after() -> None:
    assert TelegramLoginError("code_invalid").fields() == {}


def test_fields_memuat_retry_after() -> None:
    assert TelegramLoginError("flood_wait", retry_after=30).fields() == {"retry_after": 30}


@pytest.mark.parametrize("value", [None, "bukan-angka", -5, 0])
def test_retry_after_tidak_valid_jadi_nol(value: object) -> None:
    """Nilai `Flood.value` yang aneh tidak boleh membuat UI menunggu selamanya."""
    from pyrogram.errors import FloodWait

    error = map_exception(FloodWait(value))  # type: ignore[arg-type]
    assert error.retry_after == 0


# ------------------------------------------------------- migrasi sinkron


def test_upgrade_to_head_sinkron_idempoten(tmp_path: Path) -> None:
    """Jalur sinkron dipakai di luar event loop (CLI, migrasi manual)."""
    from telegent.web.db.migrate import upgrade_to_head

    url = f"sqlite+aiosqlite:///{(tmp_path / 'sync.db').as_posix()}"
    upgrade_to_head(url)
    upgrade_to_head(url)  # idempoten

    from sqlalchemy import inspect
    from sqlalchemy.engine import create_engine

    sync_url = url.replace("+aiosqlite", "")
    tables = inspect(create_engine(sync_url)).get_table_names()
    assert "app_setting" in tables
    assert "admin_user" in tables


def test_make_alembic_config_men_set_url_dan_lokasi() -> None:
    from telegent.web.db.migrate import MIGRATIONS_DIR, make_alembic_config

    config = make_alembic_config("sqlite+aiosqlite:///x.db")

    assert config.get_main_option("sqlalchemy.url") == "sqlite+aiosqlite:///x.db"
    assert config.get_main_option("script_location") == str(MIGRATIONS_DIR)


# ------------------------------------------------------- settings store


async def test_reset_to_default_menghapus_nilai_tersimpan(
    store: SettingsStore,
) -> None:
    await store.update({"max_concurrent_calls": 9}, actor="admin")
    assert await store.get("max_concurrent_calls") == 9

    await store.reset_to_default(["max_concurrent_calls"], actor="admin")

    assert await store.get("max_concurrent_calls") == 4  # kembali ke default registry


async def test_reset_kunci_tidak_dikenal_diabaikan(store: SettingsStore) -> None:
    result = await store.reset_to_default(["tidak_ada_kunci_ini"], actor="admin")
    assert result.applied == []
    assert result.needs_restart == []


async def test_nilai_setting_rusak_kembali_ke_default(
    store: SettingsStore, database: Database
) -> None:
    """JSON rusak tidak boleh menjatuhkan seluruh panel saat boot."""
    from telegent.web.db import models

    async with database.session() as session:
        session.add(
            models.AppSetting(
                key="max_concurrent_calls",
                value="{bukan-json",
                encrypted=False,
                updated_by="test",
            )
        )

    assert await store.get("max_concurrent_calls") == 4


async def test_setting_tidak_dikenal_diabaikan_saat_baca(
    store: SettingsStore, database: Database
) -> None:
    """Baris setting dari versi lama yang tak dikenal di registry diabaikan."""
    from telegent.web.db import models

    async with database.session() as session:
        session.add(
            models.AppSetting(
                key="setting_dari_masa_depan",
                value="1",
                encrypted=False,
                updated_by="test",
            )
        )

    values = await store.load_values()

    assert "setting_dari_masa_depan" not in values


async def test_import_env_hanya_satu_kali(
    store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.env` lama hanya diimpor saat database kosong (aturan migrasi §4)."""
    from telegent.config import Settings

    def _fake_settings() -> Settings:
        return Settings(
            telegram_api_id=42,
            telegram_api_hash="0123456789abcdef0123456789abcdef",
            gemini_api_key="AIzaSy0123456789012345678901234567890",
            max_concurrent_calls=7,
            _env_file=None,  # type: ignore[call-arg]
        )

    monkeypatch.setattr("telegent.web.settings_store.Settings", _fake_settings)

    assert await store.import_env_once() > 0
    assert await store.get("max_concurrent_calls") == 7

    # Panggilan kedua tidak boleh menimpa nilai yang sudah dikelola dari panel.
    await store.update({"max_concurrent_calls": 3}, actor="admin")
    assert await store.import_env_once() == 0
    assert await store.get("max_concurrent_calls") == 3


async def test_import_env_melewati_nilai_tidak_valid(
    store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nilai `.env` yang tidak valid dilewati, bukan menggagalkan impor."""
    from telegent.config import Settings

    def _fake_settings() -> Settings:
        # `Settings` sendiri tidak membatasi panjang API key, tetapi registry
        # mensyaratkan minimal 20 karakter -> harus dilewati saat impor.
        return Settings(
            telegram_api_id=42,
            telegram_api_hash="0123456789abcdef0123456789abcdef",
            gemini_api_key="pendek",
            _env_file=None,  # type: ignore[call-arg]
        )

    monkeypatch.setattr("telegent.web.settings_store.Settings", _fake_settings)

    await store.import_env_once()

    assert await store.get("telegram_api_id") == 42
    assert await store.get("gemini_api_key") == ""


async def test_import_env_gagal_saat_settings_tidak_valid(
    store: SettingsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.env` tidak ada/tidak lengkap harus dilewati diam-diam, bukan 500."""

    def _boom() -> None:
        raise ValueError("kredensial tidak lengkap")

    monkeypatch.setattr("telegent.web.settings_store.Settings", _boom)

    assert await store.import_env_once() == 0


_CREDENTIALS = {
    "telegram_api_id": 123,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}


async def test_restart_keys_pending_menandai_setting_restart(
    store: SettingsStore,
) -> None:
    """Setting yang belum dipakai runtime harus terlihat sebagai "perlu restart"."""
    await store.update(_CREDENTIALS, actor="admin")
    settings = await store.build_settings()
    assert await store.restart_keys_pending(settings) == []

    await store.update({"telegram_session_name": "sesi_lain"}, actor="admin")

    pending = await store.restart_keys_pending(settings)
    assert "telegram_session_name" in pending


async def test_restart_keys_pending_tanpa_runtime_menandai_yang_tersimpan(
    store: SettingsStore,
) -> None:
    """Saat bot belum pernah jalan, semua setting restart yang tersimpan pending."""
    await store.update({"telegram_session_name": "sesi_lain"}, actor="admin")

    pending = await store.restart_keys_pending(None)

    assert "telegram_session_name" in pending


async def test_restart_keys_pending_tidak_menandai_yang_sama(
    store: SettingsStore,
) -> None:
    await store.update(_CREDENTIALS, actor="admin")
    settings = await store.build_settings()
    await store.update({"telegram_session_name": settings.telegram_session_name}, actor="admin")

    assert await store.restart_keys_pending(settings) == []


async def test_build_settings_melempar_bila_kurang(store: SettingsStore) -> None:
    from telegent.web.settings_store import NotConfigured

    with pytest.raises(NotConfigured) as info:
        await store.build_settings()

    assert "telegram_api_id" in info.value.missing


async def test_build_settings_menunjuk_ke_direktori_data(
    database: Database, tmp_path: Path
) -> None:
    """Runtime harus menemukan `*.session` hasil login dari panel (Q10).

    `data_dir` yang sama dipakai runtime, layanan login, dan panel — kalau berbeda,
    bot tidak akan pernah menemukan sesi yang baru dibuat admin.
    """
    from telegent.web.crypto import SecretCipher

    data_dir = tmp_path / "data"
    store = SettingsStore(database, SecretCipher.for_data_dir(data_dir), data_dir=data_dir)
    await store.update(_CREDENTIALS, actor="admin")

    settings = await store.build_settings()

    assert settings.session_dir == str(data_dir)
    assert settings.allowed_user_id_set == set()


async def test_allowed_user_ids_dari_list(store: SettingsStore, tmp_path: Path) -> None:
    """UI mengirim list[int]; `Settings` mengharapkan string."""
    await store.update({**_CREDENTIALS, "allowed_user_ids": [11, 22]}, actor="admin")

    settings = await store.build_settings()

    assert settings.allowed_user_id_set == {11, 22}


async def test_update_menolak_kunci_tidak_dikenal(store: SettingsStore) -> None:
    from telegent.web.settings_registry import SettingsValidationError

    with pytest.raises(SettingsValidationError):
        await store.update({"kunci_hantu": 1}, actor="admin")


async def test_update_audit_menyimpan_masking(store: SettingsStore, database: Database) -> None:
    """Nilai secret tidak boleh masuk audit apa adanya (aturan #12)."""
    await store.update(
        {"gemini_api_key": "AIzaSyRahasiaYangPanjangSekali123"}, actor="admin"
    )

    from sqlalchemy import select

    from telegent.web.db import models

    async with database.session() as session:
        rows = (await session.execute(select(models.AuditLog))).scalars().all()

    assert rows
    for row in rows:
        assert "AIzaSyRahasiaYangPanjangSekali123" not in (row.after_json or "")
        assert "AIzaSyRahasiaYangPanjangSekali123" not in (row.before_json or "")


async def test_schema_dan_list_ui_konsisten(store: SettingsStore) -> None:
    """Metadata form harus lengkap: tiap item punya tipe, apply, dan flag secret."""
    schema = await store.schema()
    grouped = await store.list_for_ui()
    keys = {item["key"] for group in grouped for item in group["items"]}

    assert len(schema) == len(keys)
    for group in grouped:
        for item in group["items"]:
            assert item["type"]
            assert item["apply"] in {"hot", "restart"}
            assert isinstance(item["secret"], bool)
            assert "value" in item


async def test_secret_disamarkan_di_list_ui(store: SettingsStore) -> None:
    await store.update({"gemini_api_key": "AIzaSyRahasiaYangPanjangSekali123"}, actor="admin")

    grouped = await store.list_for_ui()
    nilai = next(
        item["value"]
        for group in grouped
        for item in group["items"]
        if item["key"] == "gemini_api_key"
    )

    assert "AIzaSyRahasia" not in str(nilai)