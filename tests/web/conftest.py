"""Fixture bersama untuk pengujian web panel."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from telegent.web.app import create_app
from telegent.web.bootstrap import BootstrapConfig, load_bootstrap
from telegent.web.crypto import SecretCipher
from telegent.web.db.base import Database
from telegent.web.settings_store import SettingsStore


#: Kunci environment yang tidak boleh bocor ke dalam pengujian (dikosongkan agar
#: impor `.env` developer tidak ikut berjalan).
_ISOLATED_ENV_KEYS = (
    # bootstrap web panel
    "TELEGENT_DATA_DIR",
    "TELEGENT_DB_URL",
    "TELEGENT_HOST",
    "TELEGENT_PORT",
    "TELEGENT_SESSION_TTL_HOURS",
    "TELEGENT_AUTOSTART_BOT",
    "TELEGENT_SECRET_KEY",
    "TELEGENT_FRONTEND_DIST",
    # konfigurasi runtime lama (untuk uji impor .env)
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_SESSION_NAME",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "ALLOWED_USER_IDS",
    "MAX_CONCURRENT_CALLS",
    "MAX_CALL_DURATION",
    "MAX_CALLS_PER_WINDOW",
    "CALL_WINDOW_SECONDS",
    "IDLE_ENABLED",
    "IDLE_PROMPT_SECONDS",
    "IDLE_HANGUP_SECONDS",
    "LOG_LEVEL",
    "SYSTEM_INSTRUCTION",
    "GREETING_PROMPT",
)


@pytest.fixture(autouse=True)
def _isolated_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pisahkan tes dari `.env` proyek.

    Dua sumber yang perlu dinetralkan: `load_bootstrap` (memuat `.env` ke
    environment) dan `Settings()` (pydantic-settings membaca `.env` relatif CWD).
    """
    monkeypatch.setattr("telegent.web.bootstrap.load_dotenv", lambda *a, **k: False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BootstrapConfig:
    """Konfigurasi bootstrap terisolasi (data & DB di direktori sementara)."""
    for key in _ISOLATED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return load_bootstrap(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )


@pytest.fixture
def app(bootstrap: BootstrapConfig) -> FastAPI:
    return create_app(bootstrap)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def live_client(app: FastAPI) -> Iterator[TestClient]:
    """Client dengan lifespan aktif: database, store, dan cipher siap."""
    with TestClient(app) as test_client:
        yield test_client


# ------------------------------------------------------------------ database


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """URL database sementara yang sudah termigrasi."""
    import asyncio

    from telegent.web.db.migrate import upgrade_to_head_async

    url = f"sqlite+aiosqlite:///{(tmp_path / 'unit.db').as_posix()}"
    asyncio.run(upgrade_to_head_async(url))
    return url


@pytest.fixture
async def database(db_url: str) -> AsyncIterator[Database]:
    """Database ter-migrasi untuk pengujian async."""
    db = Database(db_url)
    try:
        yield db
    finally:
        await db.dispose()


@pytest.fixture
async def store(database: Database, tmp_path: Path) -> SettingsStore:
    """SettingsStore dengan kunci enkripsi terisolasi."""
    return SettingsStore(database, SecretCipher.for_data_dir(tmp_path / "keys"))