"""Router manajemen tools bawaan (spesifikasi §6.7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from telegent.ai.tools.builtin import default_tools
from telegent.web.audit import AuditEntry, record_audit
from telegent.web.deps import AdminDep, CsrfDep, DatabaseDep, RuntimeDep
from telegent.web.errors import APIError
from telegent.web.schemas.credentials import SimpleOkResponse
from telegent.web.schemas.tools import ToolItemResponse, UpdateToolRequest
from telegent.web.tools_store import load_tool_settings, save_tool_setting

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolItemResponse])
async def list_tools(
    admin: AdminDep,
    db: DatabaseDep,
) -> list[ToolItemResponse]:
    """Daftar tool bawaan beserta status aktif dan konfigurasinya."""
    del admin
    settings = await load_tool_settings(db)

    results: list[ToolItemResponse] = []
    for spec in default_tools():
        stored = settings.get(spec.name)
        results.append(
            ToolItemResponse(
                name=spec.name,
                description=spec.description,
                enabled=stored.enabled if stored else True,
                can_disable=spec.can_disable,
                config=stored.config if stored else None,
                parameters_json_schema=spec.parameters_json_schema,
                timeout=spec.timeout,
                behavior=spec.behavior,
            )
        )
    return results


@router.put("/{name}", response_model=SimpleOkResponse)
async def update_tool(
    name: str,
    payload: UpdateToolRequest,
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    request: Request,
) -> SimpleOkResponse:
    """Perbarui status aktif atau konfigurasi satu tool."""
    spec = next((s for s in default_tools() if s.name == name), None)
    if spec is None:
        raise APIError(404, "tool_not_found", f"Tool '{name}' tidak ditemukan.")

    if payload.enabled is False and not spec.can_disable:
        raise APIError(
            400, "cannot_disable_tool", f"Tool '{name}' esensial dan tidak dapat dinonaktifkan."
        )

    client_ip = request.client.host if request.client else None

    before, after = await save_tool_setting(
        db, name, enabled=payload.enabled, config=payload.config
    )

    await record_audit(
        db,
        AuditEntry(
            action="tool.update",
            actor=admin.username,
            target=name,
            before={"enabled": before.enabled, "config": before.config},
            after={"enabled": after.enabled, "config": after.config},
            ip=client_ip,
        ),
    )

    # Berlaku ke bot yang hidup; bila bot mati, `RuntimeController` memuatnya
    # kembali dari database saat start berikutnya.
    await runtime.apply_tool_config(
        name,
        enabled=after.enabled,
        config=after.config,
    )

    return SimpleOkResponse(ok=True)