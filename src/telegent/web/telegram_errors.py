"""Katalog galat login Telegram: kode stabil + pemetaan exception Pyrogram.

Dipisah dari `telegram_login` karena satu responsibilities berbeda: modul ini
hanya dengan "apa yang salah" (kode, pesan, HTTP status), sedangkan
`telegram_login` hanya dengan "bagaimana menjalankan alurnya".
"""

from __future__ import annotations

from typing import Any

from pyrogram.errors import (
    AuthKeyUnregistered,
    Flood,
    PasswordHashInvalid,
    PhoneCodeEmpty,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberBanned,
    PhoneNumberFlood,
    PhoneNumberInvalid,
    PhoneNumberUnoccupied,
    PhonePasswordFlood,
    SessionRevoked,
)

#: Pesan cadangan (bahasa Indonesia) bila UI tidak punya terjemahan kodenya.
DEFAULT_MESSAGES: dict[str, str] = {
    "phone_invalid": "Nomor telepon tidak valid atau tidak terdaftar di Telegram.",
    "code_invalid": "Kode konfirmasi salah.",
    "code_expired": "Kode konfirmasi sudah kedaluwarsa. Minta kode baru.",
    "password_invalid": "Password 2FA salah.",
    "flood_wait": "Terlalu banyak permintaan ke Telegram. Coba lagi nanti.",
    "api_credentials_missing": "Kredensial Telegram (API ID dan API Hash) belum diisi.",
    "telegram_unreachable": "Tidak dapat terhubung ke server Telegram.",
    "session_invalid": "Sesi Telegram tidak valid lagi. Hapus sesi lalu login ulang.",
    "telegram_error": "Telegram menolak permintaan ini.",
    "already_logged_in": "Sudah ada akun Telegram yang login. Logout dulu untuk mengganti akun.",
    "account_not_logged_in": "Belum ada akun Telegram yang login.",
    "flow_not_found": "Alur login tidak ditemukan atau sudah dibatalkan.",
    "flow_expired": "Alur login sudah kedaluwarsa. Mulai lagi dari nomor telepon.",
}

#: Pemetaan exception Pyrogram → kode stabil (urut dari yang paling spesifik).
EXCEPTION_CODES: tuple[tuple[type[BaseException], str], ...] = (
    (PhoneNumberInvalid, "phone_invalid"),
    (PhoneNumberUnoccupied, "phone_invalid"),
    (PhoneNumberBanned, "phone_invalid"),
    (PhoneNumberFlood, "flood_wait"),
    (PhoneCodeInvalid, "code_invalid"),
    (PhoneCodeEmpty, "code_invalid"),
    (PhoneCodeExpired, "code_expired"),
    (PasswordHashInvalid, "password_invalid"),
    (PhonePasswordFlood, "flood_wait"),
    (AuthKeyUnregistered, "session_invalid"),
    (SessionRevoked, "session_invalid"),
)

#: Galat yang membuat status akun `error` (sesi rusak, bukan sekadar salah input).
ACCOUNT_BREAKING_CODES = frozenset({"session_invalid"})


class TelegramLoginError(RuntimeError):
    """Kegagalan login dengan **kode stabil** (bukan pesan mentah Pyrogram)."""

    def __init__(
        self,
        code: str,
        *,
        retry_after: int | None = None,
        status_code: int = 400,
        message: str | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.retry_after = retry_after
        self.status_code = status_code
        self.message = message or DEFAULT_MESSAGES.get(code, code)

    def fields(self) -> dict[str, Any]:
        """Bagian `error.fields` pada amplop galat API."""
        return {} if self.retry_after is None else {"retry_after": self.retry_after}


def _as_seconds(value: Any) -> int:
    """Ambil nilai detik dari exception Flood (aman bila bukan angka positif)."""
    try:
        seconds = int(value)  # pyright: ignore[reportArgumentType]
    except (TypeError, ValueError):
        return 0
    return seconds if seconds > 0 else 0


def map_exception(exc: BaseException) -> TelegramLoginError:
    """Terjemahkan exception apa pun menjadi `TelegramLoginError` ber-kode."""
    if isinstance(exc, Flood):
        return TelegramLoginError(
            "flood_wait",
            retry_after=_as_seconds(getattr(exc, "value", None)),
            status_code=429,
        )
    for exc_type, code in EXCEPTION_CODES:
        if isinstance(exc, exc_type):
            retry_after = (
                _as_seconds(getattr(exc, "value", None)) if code == "flood_wait" else None
            )
            status = 429 if code == "flood_wait" else 400
            return TelegramLoginError(code, retry_after=retry_after, status_code=status)
    if isinstance(exc, (OSError, TimeoutError)):
        # Kode tersendiri agar tidak bentrok dengan `network_error` generik API.
        return TelegramLoginError("telegram_unreachable", status_code=502)
    return TelegramLoginError("telegram_error", status_code=502)