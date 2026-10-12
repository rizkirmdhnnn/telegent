"""Keamanan panel: hashing password, sesi, CSRF, dan TOTP."""

from __future__ import annotations

import io
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import pyotp
import qrcode
import qrcode.image.svg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from starlette.responses import Response

from telegent.web.db.base import utcnow

log = logging.getLogger("telegent.web.security")

SESSION_COOKIE = "telegent_session"
CSRF_COOKIE = "telegent_csrf"

MIN_PASSWORD_LENGTH = 8
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

_hasher = PasswordHasher()


# ------------------------------------------------------------------- password


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_hasher.verify(password_hash, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:  # noqa: BLE001 - hash rusak tidak boleh membocorkan detail
        log.warning("Gagal memverifikasi password (hash rusak?).")
        return False


def password_problem(password: str) -> str | None:
    """Kode galat bila password tidak memenuhi syarat, atau None bila valid."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return "password_too_short"
    return None


# --------------------------------------------------------------------- sesi


@dataclass
class AdminSession:
    """Sesi admin yang aktif."""

    token: str
    csrf_token: str
    username: str
    admin_id: int
    created_at: datetime
    expires_at: datetime

    @property
    def expired(self) -> bool:
        return self.expires_at <= utcnow()


class SessionManager:
    """Penyimpanan sesi server-side di memori (single-tenant, satu admin)."""

    def __init__(self, ttl_hours: int) -> None:
        self._ttl = timedelta(hours=max(1, ttl_hours))
        self._sessions: dict[str, AdminSession] = {}

    def create(self, username: str, admin_id: int) -> AdminSession:
        now = utcnow()
        session = AdminSession(
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            username=username,
            admin_id=admin_id,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._sessions[session.token] = session
        self.purge_expired()
        return session

    def get(self, token: str | None) -> AdminSession | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        if session.expired:
            self._sessions.pop(token, None)
            return None
        return session

    def delete(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def purge_expired(self) -> int:
        now = utcnow()
        kedaluwarsa = [token for token, s in self._sessions.items() if s.expires_at <= now]
        for token in kedaluwarsa:
            self._sessions.pop(token, None)
        return len(kedaluwarsa)

    @property
    def active_count(self) -> int:
        self.purge_expired()
        return len(self._sessions)


# ------------------------------------------------------- cookie sesi & CSRF


def set_session_cookies(
    response: Response, token: str, csrf_token: str, ttl_hours: int
) -> None:
    """Pasang cookie sesi (httpOnly) dan cookie CSRF (dibaca frontend)."""
    max_age = max(1, ttl_hours) * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,  # perlu dibaca SPA untuk dikirim sebagai header
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


# ---------------------------------------------------------------------- TOTP

TOTP_ISSUER = "Telegent"


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=TOTP_ISSUER)


def verify_totp(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code:
        return False
    try:
        return bool(pyotp.TOTP(secret).verify(code, valid_window=1))
    except Exception:  # noqa: BLE001 - kode tak sah tidak boleh melempar galat
        return False


def totp_qr_svg(uri: str) -> str:
    """SVG untuk `otpauth://` URI (dibaca kamera aplikasi autentikator)."""
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")