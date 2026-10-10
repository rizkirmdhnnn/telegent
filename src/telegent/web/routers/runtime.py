"""Router status & penerapan perubahan runtime (spesifikasi §6.5).

Fase 1 baru menyediakan dua endpoint baca/terapkan yang dibutuhkan UI:
menampilkan status runtime dan menerapkan perubahan yang tertunda. Kontrol
start/stop/restart penuh menyusul pada tiket F1.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from telegent.web.audit import AuditEntry, record_audit
from telegent.web.deps import AdminDep, CsrfDep, DatabaseDep, RuntimeDep
from telegent.web.errors import APIError

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/status")
async def runtime_status(admin: AdminDep, runtime: RuntimeDep) -> dict[str, Any]:
    """Status runtime saat ini (hanya-baca)."""
    del admin
    return runtime.status().to_dict()


@router.post("/apply")
async def apply_pending(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    request: Request,
) -> dict[str, Any]:
    """Terapkan perubahan tertunda: restart bila perlu, jika tidak cukup live-apply."""
    had_pending = bool(runtime.status().pending_restart)
    status = await runtime.apply_pending()

    if had_pending:
        client_ip = request.client.host if request.client else None
        await record_audit(
            db,
            AuditEntry(
                action="runtime.apply",
                actor=admin.username,
                target="settings",
                after=status.to_dict(),
                ip=client_ip,
            ),
        )

    return status.to_dict()