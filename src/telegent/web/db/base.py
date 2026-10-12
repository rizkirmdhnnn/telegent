"""Fondasi database: engine async, sesi, PRAGMA SQLite, dan base ORM.

Catatan waktu: seluruh timestamp disimpan sebagai **naive UTC** agar konsisten
di SQLite (yang tidak menyimpan offset zona waktu). Konversi ke waktu lokal
dilakukan di sisi UI.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Konvensi nama constraint supaya migrasi batch (ALTER di SQLite) konsisten.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Timestamp UTC tanpa informasi zona waktu."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Base deklaratif untuk seluruh model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Database:
    """Engine + fabrik sesi untuk satu aplikasi."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        self.engine: AsyncEngine = create_async_engine(url, echo=echo, future=True)
        _apply_sqlite_pragmas(self.engine)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Sesi dengan commit otomatis bila blok selesai tanpa error."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """True bila koneksi database berhasil dijangkau."""
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar_one() == 1

    async def dispose(self) -> None:
        await self.engine.dispose()


def _apply_sqlite_pragmas(engine: AsyncEngine) -> None:
    """Aktifkan WAL, foreign key, dan busy timeout untuk SQLite."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()