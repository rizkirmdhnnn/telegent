"""Endpoint kesehatan publik (tanpa autentikasi)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from telegent import __version__
from telegent.web.db.base import Database

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, object]:
    """Liveness aplikasi + kesiapan database.

    `runtime` diisi pada tiket A7 (runtime controller).
    """
    db = getattr(request.app.state, "db", None)
    if isinstance(db, Database):
        db_state = "ok" if await db.ping() else "unavailable"
    else:
        db_state = "not_started"

    return {
        "ok": True,
        "service": "telegent-web",
        "version": __version__,
        "db": db_state,
    }