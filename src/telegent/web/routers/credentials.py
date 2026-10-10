"""Router kredensial API (spesifikasi §6.3)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Request

from telegent.web.deps import AdminDep, CsrfDep, RuntimeDep, StoreDep
from telegent.web.errors import APIError
from telegent.web.schemas.credentials import (
    GeminiCredentialsRequest,
    SimpleOkResponse,
    TelegramCredentialsRequest,
    ValidateCredentialsRequest,
    ValidateCredentialsResponse,
)

router = APIRouter(prefix="/credentials", tags=["credentials"])


async def _save(
    store: StoreDep,
    runtime: RuntimeDep,
    admin_username: str,
    client_ip: str | None,
    changes: dict[str, object],
) -> SimpleOkResponse:
    """Simpan hanya field yang benar-benar dikirim."""
    if not changes:
        raise APIError(400, "no_changes", "Tidak ada nilai baru untuk disimpan.")

    await store.update(changes, actor=admin_username, ip=client_ip)
    await runtime.refresh_settings()
    return SimpleOkResponse(ok=True)


@router.put("/telegram", response_model=SimpleOkResponse)
async def update_telegram_credentials(
    admin: CsrfDep,
    store: StoreDep,
    runtime: RuntimeDep,
    request: Request,
    payload: TelegramCredentialsRequest,
) -> SimpleOkResponse:
    """Simpan Telegram App api_id dan/atau api_hash (parsial)."""
    changes: dict[str, object] = {}
    if payload.api_id is not None:
        changes["telegram_api_id"] = payload.api_id
    if payload.api_hash:
        changes["telegram_api_hash"] = payload.api_hash

    return await _save(
        store,
        runtime,
        admin.username,
        request.client.host if request.client else None,
        changes,
    )


@router.put("/gemini", response_model=SimpleOkResponse)
async def update_gemini_credentials(
    admin: CsrfDep,
    store: StoreDep,
    runtime: RuntimeDep,
    request: Request,
    payload: GeminiCredentialsRequest,
) -> SimpleOkResponse:
    """Simpan Gemini API key."""
    changes: dict[str, object] = {}
    if payload.api_key:
        changes["gemini_api_key"] = payload.api_key

    return await _save(
        store,
        runtime,
        admin.username,
        request.client.host if request.client else None,
        changes,
    )


@router.post("/validate", response_model=ValidateCredentialsResponse)
async def validate_credentials(
    admin: AdminDep,
    store: StoreDep,
    payload: ValidateCredentialsRequest,
) -> ValidateCredentialsResponse:
    """Validasi format kredensial dan ketersediaan."""
    del admin
    if payload.kind == "telegram":
        api_id = await store.get("telegram_api_id")
        api_hash = await store.get("telegram_api_hash")
        if not api_id or not api_hash:
            return ValidateCredentialsResponse(
                valid=False,
                code="missing_credentials",
                message="Kredensial Telegram (API ID dan API Hash) belum diisi.",
            )
        if not isinstance(api_id, int) or api_id <= 0:
            return ValidateCredentialsResponse(
                valid=False,
                code="invalid_api_id",
                message="API ID Telegram harus berupa angka positif.",
            )
        if not re.match(r"^[0-9a-fA-F]{32}$", str(api_hash)):
            return ValidateCredentialsResponse(
                valid=False,
                code="invalid_api_hash",
                message="API Hash Telegram harus berupa 32 karakter hex.",
            )
        return ValidateCredentialsResponse(
            valid=True,
            code="valid",
            message="Kredensial Telegram valid.",
        )

    if payload.kind == "gemini":
        api_key = await store.get("gemini_api_key")
        if not api_key:
            return ValidateCredentialsResponse(
                valid=False,
                code="missing_credentials",
                message="Gemini API Key belum diisi.",
            )
        if len(str(api_key).strip()) < 20:
            return ValidateCredentialsResponse(
                valid=False,
                code="invalid_api_key",
                message="Gemini API Key terlalu pendek (minimal 20 karakter).",
            )
        return ValidateCredentialsResponse(
            valid=True,
            code="valid",
            message="Format Gemini API Key valid.",
        )

    return ValidateCredentialsResponse(
        valid=False,
        code="unknown_kind",
        message="Jenis kredensial tidak dikenal.",
    )
