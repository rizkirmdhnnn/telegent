"""Endpoint kesehatan publik (tanpa autentikasi)."""

from __future__ import annotations

from fastapi import APIRouter

from telegent import __version__

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, object]:
    """Liveness/readiness dasar.

    `db` dan `runtime` diisi pada tiket A2 (database) dan A7 (runtime controller).
    """
    return {"ok": True, "service": "telegent-web", "version": __version__}