"""Router pengaturan web panel (spesifikasi §6.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from telegent.logging_setup import set_root_level
from telegent.web.deps import (
    AdminDep,
    CallRecorderDep,
    CsrfDep,
    RuntimeDep,
    StoreDep,
)
from telegent.web.schemas.settings import (
    SettingsListResponse,
    UpdateSettingsRequest,
    UpdateSettingsResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsListResponse)
async def list_settings(
    admin: AdminDep,
    store: StoreDep,
    runtime: RuntimeDep,
) -> dict[str, Any]:
    """Ambil seluruh setting bergrup dengan secret ter-mask dan status pending restart."""
    del admin
    groups = await store.list_for_ui()
    pending = list(runtime.status().pending_restart)
    return {
        "groups": groups,
        "pending_restart": bool(pending),
        "pending_restart_keys": pending,
    }


@router.get("/schema")
async def get_settings_schema(
    admin: AdminDep,
    store: StoreDep,
) -> list[dict[str, Any]]:
    """Metadata registry seluruh setting untuk membangun form di antarmuka web."""
    del admin
    return await store.schema()


@router.put("", response_model=UpdateSettingsResponse)
async def update_settings(
    admin: CsrfDep,
    store: StoreDep,
    runtime: RuntimeDep,
    recorder: CallRecorderDep,
    request: Request,
    payload: UpdateSettingsRequest,
) -> UpdateSettingsResponse:
    """Perbarui setting secara parsial."""
    client_ip = request.client.host if request.client else None
    result = await store.update(
        payload.changes,
        actor=admin.username,
        ip=client_ip,
    )
    if "log_level" in payload.changes:
        # Level log berlaku untuk seluruh proses, bukan hanya bot; terapkan
        # seketika agar aliran `/logs/stream` ikut berubah.
        set_root_level(await store.get("log_level"))
    if "store_transcripts" in payload.changes:
        # Ditandai `hot`, jadi harus berlaku seketika: tanpa ini, toggle di UI
        # diam-diam baru berlaku setelah restart (Q13).
        recorder.set_store_transcripts(bool(await store.get("store_transcripts")))
    if result.applied or result.needs_restart:
        await runtime.refresh_settings()

    return UpdateSettingsResponse(
        applied=result.applied,
        needs_restart=result.needs_restart,
    )
