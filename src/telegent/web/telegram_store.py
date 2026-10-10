"""Penyimpanan akun & alur login Telegram (tabel `telegram_account`, `login_flow`).

Pemisahan ini menjaga `TelegramLoginService` fokus pada orkestrasi klien Pyrogram,
serta membuat akses database dapat diuji tanpa jaringan.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from telegent.web.db import models
from telegent.web.db.base import Database, utcnow

log = logging.getLogger("telegent.web.telegram_store")

#: `telegram_account` hanya menyimpan satu baris (keputusan single-tenant).
ACCOUNT_ROW_ID = 1

# Status akun (spesifikasi §5.3).
ACCOUNT_NOT_CONFIGURED = "not_configured"
ACCOUNT_LOGGED_OUT = "logged_out"
ACCOUNT_LOGGED_IN = "logged_in"
ACCOUNT_ERROR = "error"

# Status alur login (spesifikasi §5.4).
FLOW_CODE_SENT = "code_sent"
FLOW_AWAITING_PASSWORD = "awaiting_password"
FLOW_DONE = "done"


class FlowNotFound(LookupError):
    """Alur login tidak ada di database."""


class FlowExpired(LookupError):
    """Alur login ada, tetapi sudah melewati masa berlaku."""


class TelegramStore:
    """Baca/tulis baris akun tunggal dan alur login sementara."""

    def __init__(self, db: Database, *, flow_ttl: timedelta) -> None:
        self._db = db
        self._flow_ttl = flow_ttl

    # ------------------------------------------------------------------ akun

    async def load_account(self) -> models.TelegramAccount:
        """Baris akun tunggal; dibuat dengan status default bila belum ada."""
        async with self._db.session() as session:
            row = await session.get(models.TelegramAccount, ACCOUNT_ROW_ID)
            if row is not None:
                return row
            row = models.TelegramAccount(id=ACCOUNT_ROW_ID, status=ACCOUNT_NOT_CONFIGURED)
            session.add(row)
        return row

    async def update_account(self, **values: Any) -> None:
        """Tulis status akun dalam transaksi terpisah (tidak bergantung handler)."""
        async with self._db.session() as session:
            row = await session.get(models.TelegramAccount, ACCOUNT_ROW_ID)
            if row is None:
                row = models.TelegramAccount(id=ACCOUNT_ROW_ID, status=ACCOUNT_NOT_CONFIGURED)
                session.add(row)
            for key, value in values.items():
                setattr(row, key, value)

    async def set_last_error(self, error_code: str) -> None:
        """Simpan kode galat terakhir tanpa mengubah status akun."""
        await self.update_account(last_error=error_code)

    async def mark_logged_in(
        self,
        *,
        phone: str,
        session_name: str,
        user_id: int | None,
        username: str | None,
        first_name: str | None,
    ) -> None:
        await self.update_account(
            phone=phone,
            tg_user_id=user_id,
            tg_username=username,
            tg_first_name=first_name,
            session_name=session_name,
            status=ACCOUNT_LOGGED_IN,
            last_error=None,
            logged_in_at=utcnow(),
        )

    async def mark_logged_out(self, session_name: str) -> None:
        await self.update_account(
            status=ACCOUNT_LOGGED_OUT,
            tg_user_id=None,
            tg_username=None,
            tg_first_name=None,
            logged_in_at=None,
            session_name=session_name,
            last_error=None,
        )

    # ------------------------------------------------------------------ flow

    async def create_flow(self, phone: str, phone_code_hash: str) -> int:
        """Buat alur login baru; kembalikan id-nya."""
        now = utcnow()
        async with self._db.session() as session:
            flow = models.LoginFlow(
                phone=phone,
                phone_code_hash=phone_code_hash,
                status=FLOW_CODE_SENT,
                created_at=now,
                expires_at=now + self._flow_ttl,
            )
            session.add(flow)
            await session.flush()
            return int(flow.id)

    async def load_flow(self, flow_id: int) -> models.LoginFlow:
        """Ambil flow yang masih hidup; `FlowNotFound`/`FlowExpired` bila tak berlaku."""
        async with self._db.session() as session:
            flow = await session.get(models.LoginFlow, flow_id)
        if flow is None:
            raise FlowNotFound(flow_id)
        if flow.expires_at <= utcnow():
            raise FlowExpired(flow_id)
        return flow

    async def set_flow_status(self, flow_id: int, status: str) -> None:
        async with self._db.session() as session:
            flow = await session.get(models.LoginFlow, flow_id)
            if flow is not None:
                flow.status = status

    async def delete_flow(self, flow_id: int) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(models.LoginFlow).where(models.LoginFlow.id == flow_id)
            )

    async def expired_flow_ids(self) -> list[int]:
        async with self._db.session() as session:
            rows = (
                (
                    await session.execute(
                        select(models.LoginFlow.id).where(
                            models.LoginFlow.expires_at <= utcnow()
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [int(row) for row in rows]

    async def delete_all_flows(self) -> int:
        async with self._db.session() as session:
            result = await session.execute(delete(models.LoginFlow))
            return int(cast("CursorResult[Any]", result).rowcount or 0)