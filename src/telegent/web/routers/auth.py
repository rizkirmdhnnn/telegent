"""Autentikasi admin: login, sesi, profil, dan TOTP opsional."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telegent.web.db import models
from telegent.web.db.base import utcnow
from telegent.web.deps import (
    AdminDep,
    CipherDep,
    CsrfDep,
    DatabaseDep,
    get_bootstrap,
    get_sessions,
)
from telegent.web.errors import APIError
from telegent.web.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    MessageResponse,
    TotpCodeRequest,
    TotpSetupResponse,
    UpdateMeRequest,
)
from telegent.web.security import (
    LOCKOUT_MINUTES,
    MAX_FAILED_ATTEMPTS,
    SESSION_COOKIE,
    SessionManager,
    clear_session_cookies,
    generate_totp_secret,
    hash_password,
    password_problem,
    set_session_cookies,
    totp_qr_svg,
    totp_uri,
    verify_password,
    verify_totp,
)

router = APIRouter(tags=["auth"])

_VALID_LOCALES = {"id", "en"}
_VALID_THEMES = {"light", "dark", "system"}


# ------------------------------------------------------------------- helpers


async def _find_admin_by_username(session: AsyncSession, username: str) -> models.AdminUser | None:
    result = await session.execute(
        select(models.AdminUser).where(models.AdminUser.username == username)
    )
    return result.scalars().first()


async def _find_admin_by_id(session: AsyncSession, admin_id: int) -> models.AdminUser | None:
    result = await session.execute(
        select(models.AdminUser).where(models.AdminUser.id == admin_id)
    )
    return result.scalars().first()


# ---------------------------------------------------------------------- login


@router.post("/auth/login", response_model=MessageResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DatabaseDep,
    cipher: CipherDep,
) -> MessageResponse:
    """Masuk sebagai admin (password + TOTP bila aktif)."""
    username = payload.username.strip()
    now = utcnow()
    admin_id: int | None = None
    retry_after = 0
    decision = "ok"

    # Tahap 1: periksa kredensial pada sesi baca-tulis tanpa mengubah apa pun.
    async with db.session() as session:
        admin = await _find_admin_by_username(session, username)
        if admin is None:
            decision = "no_user"
        elif admin.locked_until is not None and admin.locked_until > now:
            decision = "locked"
            retry_after = int((admin.locked_until - now).total_seconds())
        elif not verify_password(admin.password_hash, payload.password):
            decision = "bad_password"
        elif admin.totp_enabled:
            secret = (
                cipher.try_decrypt(admin.totp_secret_enc)
                if admin.totp_secret_enc
                else None
            )
            if not payload.totp:
                decision = "totp_required"
            elif secret is None or not verify_totp(secret, payload.totp):
                decision = "totp_invalid"
        if admin is not None:
            admin_id = admin.id

    # Tahap 2: catat hasil percobaan pada transaksi tersendiri supaya tidak
    # ter-rollback saat galat dilempar ke pemanggil.
    locked_now = False
    if decision in ("bad_password", "ok") and admin_id is not None:
        async with db.session() as session:
            row = await _find_admin_by_id(session, admin_id)
            if row is not None:
                if decision == "bad_password":
                    row.failed_attempts += 1
                    if row.failed_attempts >= MAX_FAILED_ATTEMPTS:
                        row.failed_attempts = 0
                        row.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                        locked_now = True
                else:
                    row.failed_attempts = 0
                    row.locked_until = None
                    row.last_login_at = now

    if decision == "locked":
        raise APIError(
            423, "locked", f"Terlalu banyak percobaan. Coba lagi dalam {retry_after} detik."
        )
    if decision == "bad_password" and locked_now:
        raise APIError(
            423,
            "locked",
            f"Terlalu banyak percobaan. Akun dikunci selama {LOCKOUT_MINUTES} menit.",
        )
    if decision in ("no_user", "bad_password"):
        raise APIError(401, "invalid_credentials", "Username atau password salah.")
    if decision == "totp_required":
        raise APIError(401, "totp_required", "Kode autentikator diperlukan.")
    if decision == "totp_invalid":
        raise APIError(401, "totp_invalid", "Kode autentikator salah.")

    sessions: SessionManager = get_sessions(request)
    session = sessions.create(username, admin_id or 0)
    set_session_cookies(
        response,
        session.token,
        session.csrf_token,
        get_bootstrap(request).session_ttl_hours,
    )
    return MessageResponse(ok=True)


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response) -> MessageResponse:
    """Akhiri sesi saat ini."""
    get_sessions(request).delete(request.cookies.get(SESSION_COOKIE))
    clear_session_cookies(response)
    return MessageResponse(ok=True)


# ------------------------------------------------------------------- profil


@router.get("/auth/me", response_model=MeResponse)
async def me(admin: AdminDep, db: DatabaseDep) -> MeResponse:
    """Profil admin yang sedang masuk."""
    async with db.session() as session:
        row = await _find_admin_by_id(session, admin.admin_id)
        if row is None:  # pragma: no cover - sesi yatim setelah DB direset
            raise APIError(401, "unauthenticated", "Sesi tidak valid.")
        return MeResponse(
            username=row.username,
            totp_enabled=row.totp_enabled,
            locale=row.locale,
            theme=row.theme,
        )


@router.patch("/auth/me", response_model=MessageResponse)
async def update_me(
    payload: UpdateMeRequest, admin: CsrfDep, db: DatabaseDep
) -> MessageResponse:
    """Ubah preferensi bahasa & tema."""
    if payload.locale is not None and payload.locale not in _VALID_LOCALES:
        raise APIError(
            422,
            "invalid_choice",
            "Bahasa tidak didukung.",
            {"locale": {"choices": sorted(_VALID_LOCALES)}},
        )
    if payload.theme is not None and payload.theme not in _VALID_THEMES:
        raise APIError(
            422,
            "invalid_choice",
            "Tema tidak didukung.",
            {"theme": {"choices": sorted(_VALID_THEMES)}},
        )

    async with db.session() as session:
        row = await _find_admin_by_id(session, admin.admin_id)
        if row is None:  # pragma: no cover
            raise APIError(401, "unauthenticated", "Sesi tidak valid.")
        if payload.locale is not None:
            row.locale = payload.locale
        if payload.theme is not None:
            row.theme = payload.theme
    return MessageResponse(ok=True)


@router.post("/auth/password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest, admin: CsrfDep, db: DatabaseDep
) -> MessageResponse:
    """Ganti password admin."""
    async with db.session() as session:
        row = await _find_admin_by_id(session, admin.admin_id)
        if row is None:  # pragma: no cover
            raise APIError(401, "unauthenticated", "Sesi tidak valid.")
        if not verify_password(row.password_hash, payload.current):
            raise APIError(401, "invalid_credentials", "Password saat ini salah.")

        problem = password_problem(payload.new)
        if problem:
            raise APIError(422, problem, "Password baru tidak memenuhi syarat.")

        row.password_hash = hash_password(payload.new)
    return MessageResponse(ok=True)


# --------------------------------------------------------------------- TOTP


@router.post("/auth/totp/setup", response_model=TotpSetupResponse)
async def totp_setup(
    admin: CsrfDep, db: DatabaseDep, cipher: CipherDep
) -> TotpSetupResponse:
    """Buat secret TOTP baru (aktif setelah kode diverifikasi)."""
    secret = generate_totp_secret()
    async with db.session() as session:
        row = await _find_admin_by_id(session, admin.admin_id)
        if row is None:  # pragma: no cover
            raise APIError(401, "unauthenticated", "Sesi tidak valid.")
        row.totp_secret_enc = cipher.encrypt(secret)
        row.totp_enabled = False

    uri = totp_uri(secret, admin.username)
    return TotpSetupResponse(secret=secret, otpauth_uri=uri, qr_svg=totp_qr_svg(uri))


@router.post("/auth/totp/enable", response_model=MessageResponse)
async def totp_enable(
    payload: TotpCodeRequest, admin: CsrfDep, db: DatabaseDep, cipher: CipherDep
) -> MessageResponse:
    """Aktifkan TOTP setelah kode dari aplikasi autentikator cocok."""
    async with db.session() as session:
        row = await _find_admin_by_id(session, admin.admin_id)
        if row is None:  # pragma: no cover
            raise APIError(401, "unauthenticated", "Sesi tidak valid.")
        if not row.totp_secret_enc:
            raise APIError(400, "totp_not_setup", "Jalankan pengaturan TOTP terlebih dahulu.")

        secret = cipher.try_decrypt(row.totp_secret_enc)
        if secret is None:
            raise APIError(500, "totp_secret_broken", "Secret TOTP tidak dapat dibaca.")
        if not verify_totp(secret, payload.code):
            raise APIError(401, "totp_invalid", "Kode autentikator salah.")

        row.totp_enabled = True
    return MessageResponse(ok=True)


@router.post("/auth/totp/disable", response_model=MessageResponse)
async def totp_disable(
    payload: TotpCodeRequest, admin: CsrfDep, db: DatabaseDep, cipher: CipherDep
) -> MessageResponse:
    """Matikan TOTP setelah kode diverifikasi."""
    async with db.session() as session:
        row = await _find_admin_by_id(session, admin.admin_id)
        if row is None:  # pragma: no cover
            raise APIError(401, "unauthenticated", "Sesi tidak valid.")
        if not row.totp_enabled or not row.totp_secret_enc:
            raise APIError(400, "totp_not_enabled", "TOTP belum aktif.")

        secret = cipher.try_decrypt(row.totp_secret_enc)
        if secret is None or not verify_totp(secret, payload.code):
            raise APIError(401, "totp_invalid", "Kode autentikator salah.")

        row.totp_enabled = False
        row.totp_secret_enc = None
    return MessageResponse(ok=True)