"""Router pengaturan web panel (spesifikasi §6.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from telegent.web.deps import AdminDep, CsrfDep, RuntimeDep, StoreDep
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
    if result.applied or result.needs_restart:
        await runtime.refresh_settings()

    return UpdateSettingsResponse(
        applied=result.applied,
        needs_restart=result.needs_restart,
    )
