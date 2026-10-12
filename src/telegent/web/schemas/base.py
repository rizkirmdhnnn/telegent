"""Bentuk respons yang dipakai bersama beberapa endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class SimpleOkResponse(BaseModel):
    """Respons standar `{ok: true}` untuk aksi tanpa data balasan."""

    ok: bool = True