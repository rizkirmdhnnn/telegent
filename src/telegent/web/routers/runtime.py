"""Router kontrol runtime bot (spesifikasi §6.5, tiket F1).

Empat aksi mengubah siklus hidup bot dari panel: `start`, `stop`, `restart`,
dan `apply`. Semuanya:

- memakai **status runtime** sebagai respons (bukan `{ok: true}`) agar UI bisa
  langsung memperbarui tampilan tanpa permintaan tambahan;
- **idemoten**: klik ganda tidak merusak state (kunci internal controller);
- **selalu tercatat di audit**, sukses maupun gagal, lengkap dengan actor dan IP.

Kebijakan panggilan aktif (keputusan F1): `stop`/`restart` melakukan *graceful
drain* — panggilan aktif diberi waktu pamitan lebih dulu, bukan langsung diputus.
Jumlah panggilan yang diakhiri dikembalikan agar UI bisa menyebutkannya saat
konfirmasi.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Request

from telegent.web.audit import AuditEntry, record_audit
from telegent.web.db.base import Database
from telegent.web.deps import AdminDep, CsrfDep, DatabaseDep, RuntimeDep
from telegent.web.runtime import RuntimeController, RuntimeStatus

router = APIRouter(prefix="/runtime", tags=["runtime"])

#: Target audit untuk seluruh aksi runtime (bukan nama berkas/kunci setting).
AUDIT_TARGET = "runtime"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record(
    db: Database,
    *,
    action: str,
    actor: str,
    ip: str | None,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> None:
    """Catat hasil aksi runtime (sukses maupun gagal) ke audit log."""
    await record_audit(
        db,
        AuditEntry(
            action=action,
            actor=actor,
            target=AUDIT_TARGET,
            before=before,
            after=after,
            ip=ip,
        ),
    )


async def _run_action(
    runtime: RuntimeController,
    db: Database,
    request: Request,
    username: str,
    action: str,
    operation: Callable[[], Awaitable[RuntimeStatus]],
) -> dict[str, Any]:
    """Jalankan satu aksi runtime, catat audit, lalu kembalikan status akhirnya.

    Kegagalan tak terduga tetap dicatat lebih dulu (transaksi terpisah, sebab
    `Database.session()` me-rollback saat handler melempar), baru diteruskan.
    """
    ip = _client_ip(request)
    before = runtime.status().to_dict()
    try:
        status = await operation()
    except Exception as exc:  # noqa: BLE001 - kegagalan dicatat dulu, lalu diteruskan
        await _record(
            db,
            action=action,
            actor=username,
            ip=ip,
            before=before,
            after={"error": type(exc).__name__, "state": before["state"]},
        )
        raise
    after = status.to_dict()
    await _record(
        db,
        action=action,
        actor=username,
        ip=ip,
        before=before,
        after=after,
    )
    return after


@router.get("/status")
async def runtime_status(admin: AdminDep, runtime: RuntimeDep) -> dict[str, Any]:
    """Status runtime saat ini (hanya-baca)."""
    del admin
    return runtime.status().to_dict()


@router.post("/start")
async def start_runtime(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    request: Request,
) -> dict[str, Any]:
    """Jalankan bot.

    Bila konfigurasi atau sesi Telegram belum siap, status `not_configured` /
    `needs_login` dikembalikan (bukan galat 500) agar UI bisa mengarahkan admin.
    """
    return await _run_action(
        runtime, db, request, admin.username, "runtime.start", runtime.start
    )


@router.post("/stop")
async def stop_runtime(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    request: Request,
) -> dict[str, Any]:
    """Hentikan bot; panggilan aktif lebih dulu diakhiri graceful (drain)."""
    return await _run_action(
        runtime, db, request, admin.username, "runtime.stop", runtime.stop
    )


@router.post("/restart")
async def restart_runtime(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    request: Request,
) -> dict[str, Any]:
    """Berhenti lalu jalankan kembali dengan konfigurasi terbaru.

    Sama seperti `stop`, panggilan aktif diakhiri graceful sebelum bot mati.
    """
    return await _run_action(
        runtime, db, request, admin.username, "runtime.restart", runtime.restart
    )


@router.post("/apply")
async def apply_pending(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    request: Request,
) -> dict[str, Any]:
    """Terapkan perubahan tertunda: restart bila perlu, jika tidak cukup live-apply."""
    return await _run_action(
        runtime, db, request, admin.username, "runtime.apply", runtime.apply_pending
    )