"""Test registry setting & SettingsStore (tiket A4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from telegent.config import Settings
from telegent.web.crypto import SecretCipher
from telegent.web.db.base import Database
from telegent.web.settings_registry import (
    REGISTRY,
    ApplyMode,
    Group,
    SettingSpec,
    SettingType,
    SettingValidationError,
    specs_by_group,
)
from telegent.web.settings_store import NotConfigured, SettingsStore, SettingsValidationError

_CREDENTIALS = {
    "telegram_api_id": 12345678,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}


@pytest.fixture
async def store(database: Database, tmp_path: Path) -> SettingsStore:
    """Store terisolasi (kunci enkripsi sendiri per pengujian)."""
    return SettingsStore(database, SecretCipher.for_data_dir(tmp_path / "keys"))


# ------------------------------------------------------------------- registry


def test_registry_mencakup_semua_setting_yang_dijanjikan() -> None:
    wajib = {
        "telegram_api_id",
        "telegram_api_hash",
        "gemini_api_key",
        "telegram_session_name",
        "gemini_model",
        "system_instruction",
        "greeting_prompt",
        "idle_prompt_instruction",
        "idle_farewell_instruction",
        "allowed_user_ids",
        "max_concurrent_calls",
        "max_call_duration",
        "max_calls_per_window",
        "call_window_seconds",
        "idle_enabled",
        "idle_prompt_seconds",
        "idle_hangup_seconds",
        "log_level",
        "bot_autostart",
        "calls_retention_days",
        "transcripts_retention_days",
        "store_transcripts",
        "log_buffer_lines",
        "tg_sample_rate",
        "tg_frame_ms",
        "gemini_input_rate",
        "gemini_output_rate",
    }
    assert wajib <= set(REGISTRY)


def test_kredensial_butuh_restart_selainnya_hot() -> None:
    for key in ("telegram_api_id", "telegram_api_hash", "gemini_api_key"):
        assert REGISTRY[key].apply is ApplyMode.RESTART
    assert REGISTRY["max_concurrent_calls"].apply is ApplyMode.HOT
    assert REGISTRY["system_instruction"].apply is ApplyMode.HOT


def test_registry_terkelompok_dan_ada_default_penanda() -> None:
    grouped = specs_by_group()
    assert set(grouped) >= {g.value for g in Group}
    assert REGISTRY["system_instruction"].default  # persona punya default kode
    assert REGISTRY["gemini_model"].default == "gemini-3.1-flash-live-preview"


def test_secret_hanya_untuk_nilai_kredensial() -> None:
    secrets = {key for key, spec in REGISTRY.items() if spec.secret}
    assert secrets == {"telegram_api_id", "telegram_api_hash", "gemini_api_key"}


# ------------------------------------------------------------------ coercion


def test_coerce_tipe_dasar() -> None:
    assert REGISTRY["max_concurrent_calls"].coerce("6") == 6
    assert REGISTRY["max_concurrent_calls"].coerce(7) == 7
    assert REGISTRY["max_call_duration"].coerce("120") == 120.0
    assert REGISTRY["idle_enabled"].coerce("false") is False
    assert REGISTRY["idle_enabled"].coerce(True) is True
    assert REGISTRY["log_level"].coerce("debug") == "DEBUG"


def test_coerce_daftar_id_dari_berbagai_format() -> None:
    spec = REGISTRY["allowed_user_ids"]
    assert spec.coerce("1,2;3") == [1, 2, 3]
    assert spec.coerce([4, 5]) == [4, 5]
    assert spec.coerce("") == []
    assert spec.coerce(None) == []


@pytest.mark.parametrize(
    ("key", "nilai", "kode"),
    [
        ("max_concurrent_calls", 0, "too_small"),
        ("max_concurrent_calls", "abc", "invalid_int"),
        ("max_call_duration", -1, "too_small"),
        ("call_window_seconds", 0, "too_small"),
        ("idle_enabled", "mungkin", "invalid_bool"),
        ("log_level", "VERBOSE", "invalid_choice"),
        ("gemini_api_key", "pendek", "too_short"),
        ("telegram_api_hash", "bukan-hex", "invalid_format"),
        ("allowed_user_ids", "1,x", "invalid_int_list"),
    ],
)
def test_coerce_menolak_nilai_tidak_valid(key: str, nilai: object, kode: str) -> None:
    with pytest.raises(SettingValidationError) as exc:
        REGISTRY[key].coerce(nilai)
    assert exc.value.code == kode
    assert exc.value.key == key


def test_schema_metadata_tidak_membocorkan_default_secret() -> None:
    meta = next(s for s in (REGISTRY[k].to_schema() for k in REGISTRY) if s["key"] == "gemini_api_key")
    assert meta["secret"] is True
    assert meta["apply"] == "restart"
    assert "default" not in meta


def test_spec_label_default_terisi_otomatis() -> None:
    spec = SettingSpec(
        key="contoh", type=SettingType.TEXT, group=Group.LOGGING, apply=ApplyMode.HOT, default="x"
    )
    assert spec.label == "settings.contoh"
    assert spec.description == "settings.contoh.help"


# -------------------------------------------------------------------- store


async def test_awal_belum_terkonfigurasi(store: SettingsStore) -> None:
    assert await store.is_configured() is False
    assert await store.missing_required() == [
        "telegram_api_id",
        "telegram_api_hash",
        "gemini_api_key",
    ]
    with pytest.raises(NotConfigured):
        await store.build_settings()


async def test_update_lalu_build_settings(store: SettingsStore) -> None:
    result = await store.update(
        {**_CREDENTIALS, "max_concurrent_calls": "8", "allowed_user_ids": "11,22"}
    )
    assert set(result.applied) == {"max_concurrent_calls", "allowed_user_ids"}
    assert set(result.needs_restart) == set(_CREDENTIALS)
    assert await store.is_configured() is True

    settings = await store.build_settings()
    assert settings.max_concurrent_calls == 8
    assert settings.allowed_user_id_set == {11, 22}
    assert settings.telegram_api_id == 12345678


async def test_update_menolak_kunci_tak_dikenal(store: SettingsStore) -> None:
    with pytest.raises(SettingsValidationError) as exc:
        await store.update({"nilai_ngawur": 1})
    assert exc.value.errors[0].code == "unknown_key"


async def test_update_mengumpulkan_semua_galat(store: SettingsStore) -> None:
    with pytest.raises(SettingsValidationError) as exc:
        await store.update({"max_concurrent_calls": 0, "log_level": "NYARIS"})
    kode = {err.key: err.code for err in exc.value.errors}
    assert kode == {"max_concurrent_calls": "too_small", "log_level": "invalid_choice"}
    # Tidak ada yang tersimpan bila ada galat.
    assert await store.load_values() == {**{k: s.default for k, s in REGISTRY.items()}}


async def test_secret_tersimpan_terenkripsi(store: SettingsStore) -> None:
    await store.update(_CREDENTIALS, actor="admin")

    from sqlalchemy import select

    from telegent.web.db import models

    async with store._db.session() as session:  # noqa: SLF001 - verifikasi internal
        rows = (
            await session.execute(select(models.AppSetting))
        ).scalars().all()
    by_key = {row.key: row for row in rows}
    assert by_key["gemini_api_key"].encrypted is True
    assert "AIza" not in by_key["gemini_api_key"].value
    assert by_key["gemini_api_key"].updated_by == "admin"


async def test_list_for_ui_menyamarkan_secret(store: SettingsStore) -> None:
    await store.update(_CREDENTIALS)

    grouped = await store.list_for_ui()
    items = {item["key"]: item for group in grouped for item in group["items"]}

    assert items["gemini_api_key"]["secret"] is True
    assert items["gemini_api_key"]["is_set"] is True
    assert str(_CREDENTIALS["gemini_api_key"]) not in str(items["gemini_api_key"]["value"])

    assert items["max_concurrent_calls"]["value"] == 4  # nilai default
    assert items["max_concurrent_calls"]["is_set"] is False


async def test_schema_untuk_ui(store: SettingsStore) -> None:
    schema = await store.schema()
    keys = {row["key"] for row in schema}
    assert "max_concurrent_calls" in keys
    assert all({"key", "type", "group", "apply", "label"} <= set(row) for row in schema)


async def test_reset_ke_default(store: SettingsStore) -> None:
    await store.update({**_CREDENTIALS, "max_concurrent_calls": 9})
    await store.reset_to_default(["max_concurrent_calls"])

    assert await store.get("max_concurrent_calls") == 4
    settings = await store.build_settings()
    assert settings.max_concurrent_calls == 4


async def test_restart_keys_pending(store: SettingsStore) -> None:
    await store.update(_CREDENTIALS)

    # Belum ada runtime: semua setting restart yang tersimpan tertunda.
    assert set(await store.restart_keys_pending(None)) == set(_CREDENTIALS)

    # Setelah runtime memakai nilai tersimpan, tidak ada yang tertunda.
    current = await store.build_settings()
    assert await store.restart_keys_pending(current) == []

    # Setelah nilai diubah di DB, kembali tertunda.
    await store.update({"telegram_api_hash": "f" * 32})
    assert await store.restart_keys_pending(current) == ["telegram_api_hash"]


async def test_pengaturan_aplikasi_tidak_masuk_settings(store: SettingsStore) -> None:
    await store.update({**_CREDENTIALS, "store_transcripts": False, "log_buffer_lines": 500})
    settings = await store.build_settings()
    assert not hasattr(settings, "store_transcripts")
    assert await store.get("store_transcripts") is False


async def test_default_persona_dipakai_bila_belum_diatur(store: SettingsStore) -> None:
    await store.update(_CREDENTIALS)
    settings = await store.build_settings()
    assert settings.system_instruction
    assert settings.greeting_prompt


# ------------------------------------------------------- impor dari .env lama


async def test_import_env_legacy_satu_kali(
    store: SettingsStore, tmp_path: Path, monkeypatch
) -> None:
    legacy_env = (
        "TELEGRAM_API_ID=999\n"
        "TELEGRAM_API_HASH=" + ("a" * 32) + "\n"
        "GEMINI_API_KEY=AIzaLegacy012345678901234567890\n"
        "MAX_CONCURRENT_CALLS=7\n"
        "SYSTEM_INSTRUCTION=Saya asisten Tes.\n"
    )
    env_file = tmp_path / ".env.legacy"
    env_file.write_text(legacy_env, encoding="utf-8")

    for key in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "GEMINI_API_KEY", "MAX_CONCURRENT_CALLS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)

    jumlah = await store.import_env_once()
    assert jumlah >= 3

    settings = await store.build_settings()
    assert settings.telegram_api_id == 999
    assert settings.max_concurrent_calls == 7
    assert settings.system_instruction == "Saya asisten Tes."

    # Jalankan lagi: tidak menimpa nilai yang sudah ada di DB.
    await store.update({"max_concurrent_calls": 2})
    assert await store.import_env_once() == 0
    assert (await store.build_settings()).max_concurrent_calls == 2


async def test_import_env_tanpa_kredensial_aman(store: SettingsStore, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
    for key in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)

    assert await store.import_env_once() == 0


# ------------------------------------------------------------------ integrasi


def test_settings_store_tersedia_di_app(bootstrap) -> None:
    from fastapi.testclient import TestClient

    from telegent.web.app import create_app

    with TestClient(create_app(bootstrap)) as client:
        assert client.get("/api/healthz").status_code == 200
        # Store terpasang (belum dipakai router sampai tiket C1).
        assert bootstrap.db_url


async def test_settings_dibangun_dari_db_dan_env_diabaikan(store: SettingsStore, monkeypatch) -> None:
    """Setelah tersimpan, nilai DB mengalahkan nilai environment."""
    await store.update({**_CREDENTIALS, "max_concurrent_calls": 3})
    monkeypatch.setenv("MAX_CONCURRENT_CALLS", "99")
    monkeypatch.setenv("TELEGRAM_API_ID", "1")

    settings: Settings = await store.build_settings()
    assert settings.max_concurrent_calls == 3
    assert settings.telegram_api_id == 12345678