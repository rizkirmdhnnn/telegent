"""Router akun & login Telegram (spesifikasi §6.4, tiket D2).

Endpoint ini menjadi satu-satunya jalan admin untuk menghubungkan akun Telegram.
Setiap mutasi memerlukan sesi admin + CSRF dan dicatat pada audit log dengan
**hanya kode langkah** — nomor telepon, kode OTP, password, dan `phone_code_hash`
tidak pernah masuk `before`/`after`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import APIRouter, Request

from telegent.web.audit import AuditEntry, record_audit
from telegent.web.deps import (
    AdminDep,
    CsrfDep,
    DatabaseDep,
    RuntimeDep,
    TelegramLoginDep,
)
from telegent.web.errors import APIError
from telegent.web.runtime import RuntimeController, RuntimeState
from telegent.web.schemas.telegram import (
    LoginCancelRequest,
    LoginNext,
    LoginPasswordRequest,
    LoginStartRequest,
    LoginStartResponse,
    LoginVerifyRequest,
    LoginVerifyResponse,
    SimpleOkResponse,
)
from telegent.web.telegram_errors import TelegramLoginError

router = APIRouter(prefix="/telegram", tags=["telegram"])

#: Target audit: akun tunggal, bukan nama berkas sesi.
AUDIT_TARGET = "account"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _ensure_bot_stopped(runtime: RuntimeController) -> None:
    """Login/logout butuh berkas sesi yang tidak sedang dipakai bot.

    `status()` adalah sumber kebenaran tunggal; `state` hanya dibaca sebagai
    project's ulang agar transisi STARTING/STOPPING ikut tertangkap.
    """
    status = runtime.status()
    if status.running or runtime.state in (RuntimeState.RUNNING, RuntimeState.STARTING):
        raise APIError(
            409,
            "bot_running",
            "Bot sedang berjalan. Hentikan bot sebelum mengganti akun Telegram.",
        )


def _to_api_error(exc: TelegramLoginError) -> APIError:
    """Terjemahkan galat layanan menjadi galat API dengan kode & retry_after."""
    return APIError(exc.status_code, exc.code, exc.message, exc.fields() or None)


async def _audit(
    db: DatabaseDep,
    actor: str,
    action: str,
    *,
    ip: str | None,
    before: Any = None,
    after: Any = None,
) -> None:
    """Catat aksi login/logout; nilai yang ditulis hanya kode langkah/kondisi."""
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


@asynccontextmanager
async def _login_step(
    db: DatabaseDep,
    actor: str,
    step: str,
    *,
    ip: str | None,
    flow_id: int | None = None,
    before: Any = None,
) -> AsyncIterator[None]:
    """Konteks satu langkah login: catat audit lalu teruskan, atau catat galat & lempar.

    Menyatukan pola `try/except → audit → raise` yang sebelumnya diulang di lima
    handler; nilai yang ditulis ke audit hanya kode langkah dan kode galat.
    """
    detail: dict[str, Any] = {"step": step}
    if flow_id is not None:
        detail["flow_id"] = flow_id
    try:
        yield
    except TelegramLoginError as exc:
        await _audit(db, actor, "telegram.login", ip=ip, before=before, after={**detail, "error": exc.code})
        raise _to_api_error(exc) from exc
    await _audit(db, actor, "telegram.login", ip=ip, before=before, after=detail)


@router.get("/status")
async def telegram_status(
    admin: AdminDep,
    service: TelegramLoginDep,
) -> dict[str, Any]:
    """Status akun Telegram saat ini (kredensial, sesi, galat terakhir)."""
    del admin  # dependency mewajibkan sesi admin, bukan untuk datanya
    return await service.status()


@router.post("/login/start", response_model=LoginStartResponse)
async def login_start(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    service: TelegramLoginDep,
    request: Request,
    payload: LoginStartRequest,
) -> LoginStartResponse:
    """Mulai alur login: kirim kode OTP ke nomor yang diberikan."""
    _ensure_bot_stopped(runtime)
    start: Any = None
    async with _login_step(db, admin.username, "start", ip=_client_ip(request)):
        start = await service.start(payload.phone)
    return LoginStartResponse(flow_id=start.flow_id, next=cast(LoginNext, start.next))


@router.post("/login/verify", response_model=LoginVerifyResponse)
async def login_verify(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    service: TelegramLoginDep,
    request: Request,
    payload: LoginVerifyRequest,
) -> LoginVerifyResponse:
    """Verifikasi kode OTP; mungkin lanjut ke langkah password 2FA."""
    _ensure_bot_stopped(runtime)
    async with _login_step(
        db, admin.username, "verify", ip=_client_ip(request), flow_id=payload.flow_id
    ):
        result = await service.verify(payload.flow_id, payload.code)
    return LoginVerifyResponse(next=cast(LoginNext, result.next))


@router.post("/login/password", response_model=SimpleOkResponse)
async def login_password(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    service: TelegramLoginDep,
    request: Request,
    payload: LoginPasswordRequest,
) -> SimpleOkResponse:
    """Kirim password 2FA untuk flow yang sedang menunggu."""
    _ensure_bot_stopped(runtime)
    async with _login_step(
        db, admin.username, "password", ip=_client_ip(request), flow_id=payload.flow_id
    ):
        await service.submit_password(payload.flow_id, payload.password)
    return SimpleOkResponse(ok=True)


@router.post("/login/cancel", response_model=SimpleOkResponse)
async def login_cancel(
    admin: CsrfDep,
    db: DatabaseDep,
    service: TelegramLoginDep,
    request: Request,
    payload: LoginCancelRequest,
) -> SimpleOkResponse:
    """Batalkan alur login yang belum selesai."""
    async with _login_step(
        db, admin.username, "cancel", ip=_client_ip(request), flow_id=payload.flow_id
    ):
        await service.cancel(payload.flow_id)
    return SimpleOkResponse(ok=True)


@router.post("/logout", response_model=SimpleOkResponse)
async def telegram_logout(
    admin: CsrfDep,
    db: DatabaseDep,
    runtime: RuntimeDep,
    service: TelegramLoginDep,
    request: Request,
) -> SimpleOkResponse:
    """Akhiri sesi Telegram dan hapus berkas `*.session`."""
    _ensure_bot_stopped(runtime)
    ip = _client_ip(request)
    before = (await service.status()).get("status")
    try:
        result = await service.logout()
    except TelegramLoginError as exc:
        await _audit(
            db,
            admin.username,
            "telegram.logout",
            ip=ip,
            before={"status": before},
            after={"error": exc.code},
        )
        raise _to_api_error(exc) from exc


    await _audit(
        db,
        admin.username,
        "telegram.logout",
        ip=ip,
        before={"status": before},
        after={"status": "logged_out", "telegram_error": result["remote_error"]},
    )
    return SimpleOkResponse(ok=True)