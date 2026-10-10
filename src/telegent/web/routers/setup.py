"""Wizard pengaturan awal: membuat akun admin pertama."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from telegent.web.db import models
from telegent.web.db.base import Database
from telegent.web.deps import DatabaseDep, get_bootstrap, get_sessions
from telegent.web.errors import APIError
from telegent.web.schemas.auth import CreateAdminRequest, SetupStatus
from telegent.web.security import (
    SessionManager,
    hash_password,
    password_problem,
    set_session_cookies,
)

router = APIRouter(tags=["setup"])


async def _get_single_admin(db: Database) -> models.AdminUser | None:
    from sqlalchemy import select

    async with db.session() as session:
        result = await session.execute(select(models.AdminUser).limit(1))
        return result.scalars().first()


@router.get("/setup/status", response_model=SetupStatus)
async def setup_status(db: DatabaseDep) -> SetupStatus:
    """True bila admin belum pernah dibuat."""
    return SetupStatus(needs_setup=await _get_single_admin(db) is None)


@router.post("/setup/admin")
async def create_admin(
    payload: CreateAdminRequest,
    request: Request,
    response: Response,
    db: DatabaseDep,
) -> dict[str, bool]:
    """Buat admin pertama. Menolak bila admin sudah ada."""
    if await _get_single_admin(db) is not None:
        raise APIError(409, "already_setup", "Admin sudah pernah dibuat.")

    username = payload.username.strip()
    if not username:
        raise APIError(422, "validation_error", "Username tidak boleh kosong.")

    problem = password_problem(payload.password)
    if problem:
        raise APIError(422, problem, "Password tidak memenuhi syarat.")

    async with db.session() as session:
        admin = models.AdminUser(
            username=username, password_hash=hash_password(payload.password)
        )
        session.add(admin)
        await session.flush()
        admin_id = admin.id

    # Login otomatis agar wizard dapat lanjut.
    sessions: SessionManager = get_sessions(request)
    session = sessions.create(username, admin_id)
    set_session_cookies(
        response, session.token, session.csrf_token, get_bootstrap(request).session_ttl_hours
    )
    return {"ok": True}