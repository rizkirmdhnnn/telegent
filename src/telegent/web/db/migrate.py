"""Pembungkus Alembic: menjalankan migrasi ke `head` saat aplikasi boot.

Alembic untuk driver async (``aiosqlite``) memanggil ``asyncio.run()`` di dalam
``env.py``. Karena itu migrasi **tidak boleh** dijalankan langsung dari dalam event
loop yang sudah aktif (mis. lifespan FastAPI). `upgrade_to_head_async` menjalankan
migrasi di thread terpisah agar tidak konflik.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger("telegent.web.db")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def make_alembic_config(db_url: str) -> Config:
    """Konfigurasi Alembic terprogram dengan URL database dari bootstrap."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def upgrade_to_head(db_url: str) -> None:
    """Terapkan seluruh migrasi (idempoten). Hanya untuk konteks sinkron."""
    log.info("Menjalankan migrasi database ke head.")
    command.upgrade(make_alembic_config(db_url), "head")


async def upgrade_to_head_async(db_url: str) -> None:
    """Versi awaitable yang aman dipanggil dari dalam event loop."""
    log.info("Menjalankan migrasi database ke head.")
    await asyncio.to_thread(command.upgrade, make_alembic_config(db_url), "head")