"""Konfigurasi bootstrap web panel (hanya yang dibutuhkan sebelum DB tersedia).

Nilai di sini dibaca dari environment. Semua konfigurasi aplikasi lainnya disimpan
di database (lihat `telegent.web.settings_store`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_DATA_DIR = "./data"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_SESSION_TTL_HOURS = 168
DEFAULT_DB_FILENAME = "telegent.db"

#: Nama env yang mengaktifkan mode fake (lihat `telegent.web.fake`).
FAKE_ENV = "TELEGENT_FAKE"

# Lokasi hasil build SPA: repo (pengembangan) atau di dalam paket (produksi).
_REPO_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "build"
_PACKAGED_FRONTEND_DIST = Path(__file__).resolve().parent / "static"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _resolve_frontend_dist() -> Path:
    """Cari hasil build SPA; fallback ke lokasi di dalam paket."""
    override = os.getenv("TELEGENT_FRONTEND_DIST")
    if override:
        return Path(override).expanduser().resolve()
    if _REPO_FRONTEND_DIST.is_dir():
        return _REPO_FRONTEND_DIST
    return _PACKAGED_FRONTEND_DIST


@dataclass(frozen=True)
class BootstrapConfig:
    """Nilai bootstrap yang dibutuhkan sebelum store/database siap."""

    data_dir: Path
    db_url: str
    secret_key: str | None
    host: str
    port: int
    session_ttl_hours: int
    autostart_bot: bool
    frontend_dist: Path
    #: Mode fake (bot & klien Telegram tiruan) — hanya lewat env `TELEGENT_FAKE=1`.
    fake: bool = False

    @property
    def db_path(self) -> Path:
        """Lokasi berkas SQLite (hanya relevan bila `db_url` berupa SQLite)."""
        return self.data_dir / DEFAULT_DB_FILENAME

    @property
    def has_frontend(self) -> bool:
        """True bila hasil build SPA tersedia untuk dilayani."""
        return (self.frontend_dist / "index.html").is_file()

    def ensure_data_dir(self) -> Path:
        """Buat direktori data bila belum ada; kembalikan path-nya."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


def load_bootstrap(
    *,
    data_dir: Path | None = None,
    db_url: str | None = None,
) -> BootstrapConfig:
    """Baca konfigurasi bootstrap dari environment.

    Argumen `data_dir`/`db_url` dipakai oleh pengujian untuk mengisolasi state.
    """
    resolved_dir = (
        data_dir
        if data_dir is not None
        else Path(os.getenv("TELEGENT_DATA_DIR", DEFAULT_DATA_DIR)).expanduser()
    ).resolve()

    # Mode fake dibaca SEBELUM `load_dotenv` danlangsung dari environment proses:
    # file `.env` tidak boleh pernah mengaktifkan mode tiruan.
    fake = os.environ.get(FAKE_ENV, "").strip() == "1"

    # `.env` hanya sebagai fallback; variabel environment asli selalu menang.
    load_dotenv(override=False)

    resolved_db_url = db_url or os.getenv("TELEGENT_DB_URL") or ""
    if not resolved_db_url:
        resolved_db_url = f"sqlite+aiosqlite:///{(resolved_dir / DEFAULT_DB_FILENAME).as_posix()}"

    secret_key = os.getenv("TELEGENT_SECRET_KEY") or None

    return BootstrapConfig(
        data_dir=resolved_dir,
        db_url=resolved_db_url,
        secret_key=secret_key,
        host=os.getenv("TELEGENT_HOST", DEFAULT_HOST),
        port=_env_int("TELEGENT_PORT", DEFAULT_PORT),
        session_ttl_hours=_env_int("TELEGENT_SESSION_TTL_HOURS", DEFAULT_SESSION_TTL_HOURS),
        autostart_bot=_env_bool("TELEGENT_AUTOSTART_BOT", True),
        frontend_dist=_resolve_frontend_dist(),
        fake=fake,
    )