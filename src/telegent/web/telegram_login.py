"""Layanan login Telegram programatik (spesifikasi §8.4, tiket D1).

Modul ini membungkus klien Pyrogram **tak-terautentikasi** agar admin dapat
menghubungkan akun Telegram dari panel web: kirim kode → verifikasi kode →
(bila perlu) password 2FA. Setelah berhasil, berkas `*.session` tersimpan di
`TELEGENT_DATA_DIR` dan siap dipakai runtime bot.

Prinsip yang dijaga di sini:

- **Kode galat stabil.** Semua kegagalan dipetakan ke kode (bukan pesan mentah
  Pyrogram) supaya UI bisa menerjemahkan; `FloodWait` membawa `retry_after`.
- **Rahasia tidak pernah masuk log.** `phone_code_hash`, kode OTP, dan password
  tidak pernah menjadi argumen pemanggilan `log`; nilainya didaftarkan ke
  `SecretRedactor` sebagai pengaman kedua.
- **Tidak menyentuh jaringan saat diuji.** Klien dibuat lewat `ClientFactory`;
  tes meng-*stub* `Client` pada modul ini.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, cast

from pyrogram import Client
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
    SessionPasswordNeeded,
    SessionRevoked,
)
from sqlalchemy import CursorResult, delete, select

from telegent.web.db import models
from telegent.web.db.base import Database, utcnow
from telegent.web.log_stream import SecretRedactor
from telegent.web.settings_store import SettingsStore

log = logging.getLogger("telegent.web.telegram")

#: Umur maksimum satu alur login sebelum dibuang (±10 menit).
LOGIN_FLOW_TTL = timedelta(minutes=10)
#: Jeda antar pembersihan `login_flow` kedaluwarsa.
CLEANUP_INTERVAL_SEC = 300.0
#: `telegram_account` hanya menyimpan satu baris (keputusan single-tenant).
ACCOUNT_ROW_ID = 1
#: Nama sesi cadangan bila setting `telegram_session_name` kosong.
DEFAULT_SESSION_NAME = "userbot_session"

# Status akun (spesifikasi §5.3).
ACCOUNT_NOT_CONFIGURED = "not_configured"
ACCOUNT_LOGGED_OUT = "logged_out"
ACCOUNT_LOGGED_IN = "logged_in"
ACCOUNT_ERROR = "error"

# Status alur login (spesifikasi §5.4).
FLOW_CODE_SENT = "code_sent"
FLOW_AWAITING_PASSWORD = "awaiting_password"
FLOW_DONE = "done"

# Nilai langkah berikutnya pada respons API.
NEXT_CODE = "code"
NEXT_PASSWORD = "password"
NEXT_DONE = "done"

#: Pabrik klien Pyrogram: `(session_name, api_id, api_hash, workdir)` → klien.
ClientFactory = Callable[[str, int, str, Path], Any]

_PHONE_NON_DIGITS = re.compile(r"[^0-9]")
_PHONE_FORMAT = re.compile(r"^\+?[0-9]{8,15}$")

#: Pesan cadangan (bahasa Indonesia) bila UI tidak punya terjemahan kodenya.
DEFAULT_MESSAGES: dict[str, str] = {
    "phone_invalid": "Nomor telepon tidak valid atau tidak terdaftar di Telegram.",
    "code_invalid": "Kode konfirmasi salah.",
    "code_expired": "Kode konfirmasi sudah kedaluwarsa. Minta kode baru.",
    "password_invalid": "Password 2FA salah.",
    "flood_wait": "Terlalu banyak permintaan ke Telegram. Coba lagi nanti.",
    "api_credentials_missing": "Kredensial Telegram (API ID dan API Hash) belum diisi.",
    "network_error": "Tidak dapat terhubung ke Telegram.",
    "session_invalid": "Sesi Telegram tidak valid lagi. Hapus sesi lalu login ulang.",
    "telegram_error": "Telegram menolak permintaan ini.",
    "already_logged_in": "Sudah ada akun Telegram yang login. Logout dulu untuk mengganti akun.",
    "account_not_logged_in": "Belum ada akun Telegram yang login.",
    "flow_not_found": "Alur login tidak ditemukan atau sudah dibatalkan.",
    "flow_expired": "Alur login sudah kedaluwarsa. Mulai lagi dari nomor telepon.",
}

#: Pemetaan exception Pyrogram → kode stabil (urut dari yang paling spesifik).
_EXCEPTION_CODES: tuple[tuple[type[BaseException], str], ...] = (
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

#: Galat yang berarti "langkah berikutnya butuh password 2FA".
_SESSION_PASSWORD_EXCEPTIONS = (SessionPasswordNeeded,)

#: Galat yang membuat status akun `error` (sesi rusak, bukan sekadar salah input).
_ACCOUNT_BREAKING_CODES = frozenset({"session_invalid"})


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
    for exc_type, code in _EXCEPTION_CODES:
        if isinstance(exc, exc_type):
            retry_after = (
                _as_seconds(getattr(exc, "value", None)) if code == "flood_wait" else None
            )
            status = 429 if code == "flood_wait" else 400
            return TelegramLoginError(code, retry_after=retry_after, status_code=status)
    if isinstance(exc, (OSError, TimeoutError)):
        return TelegramLoginError("network_error", status_code=502)
    return TelegramLoginError("telegram_error", status_code=502)


def normalize_phone(phone: str) -> str:
    """Bersihkan nomor telepon ke format internasional; validasi awal (tanpa jaringan)."""
    candidate = phone.strip()
    if not candidate:
        raise TelegramLoginError("phone_invalid")
    body = candidate[1:] if candidate[0] == "+" else candidate
    cleaned = "+" + _PHONE_NON_DIGITS.sub("", body)
    if not _PHONE_FORMAT.fullmatch(cleaned):
        raise TelegramLoginError("phone_invalid")
    return cleaned


def normalize_code(code: str) -> str:
    """Bersihkan kode OTP (hanya digit); validasi awal tanpa menyentuh jaringan."""
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit() or not 2 <= len(cleaned) <= 10:
        raise TelegramLoginError("code_invalid")
    return cleaned


@dataclass(frozen=True)
class LoginStart:
    """Hasil `start()`: flow baru siap menerima kode OTP."""

    flow_id: int
    next: str = NEXT_CODE


@dataclass(frozen=True)
class LoginResult:
    """Hasil verifikasi kode: langkah berikutnya (`password` atau `done`)."""

    next: str


def _default_client_factory(
    session_name: str, api_id: int, api_hash: str, workdir: Path
) -> Any:
    """Bangun klien Pyrogram tak-terautentikasi (tanpa nomor telepon)."""
    return Client(
        session_name,
        api_id=api_id,
        api_hash=api_hash,
        workdir=str(workdir),
        no_updates=True,
    )


class TelegramLoginService:
    """Kelola klien login sekali-pakai + status akun Telegram di database."""

    def __init__(
        self,
        db: Database,
        store: SettingsStore,
        *,
        data_dir: Path,
        redactor: SecretRedactor | None = None,
        client_factory: ClientFactory | None = None,
        flow_ttl: timedelta = LOGIN_FLOW_TTL,
    ) -> None:
        self._db = db
        self._store = store
        self._data_dir = Path(data_dir)
        self._redactor = redactor
        self._client_factory = client_factory or _default_client_factory
        self._flow_ttl = flow_ttl
        self._clients: dict[int, Any] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- kredensial

    async def _load_credentials(self) -> tuple[int | None, str, str]:
        """(api_id, api_hash, session_name) apa adanya dari store."""
        values = await self._store.load_values()
        api_id = values.get("telegram_api_id")
        api_hash = values.get("telegram_api_hash") or ""
        session_name = str(values.get("telegram_session_name") or DEFAULT_SESSION_NAME)
        return (api_id if isinstance(api_id, int) else None), str(api_hash), session_name

    async def credentials(self) -> tuple[int, str, str]:
        """Kredensial siap pakai; galat `api_credentials_missing` bila belum lengkap."""
        api_id, api_hash, session_name = await self._load_credentials()
        if not api_id or api_id <= 0 or not api_hash:
            raise TelegramLoginError("api_credentials_missing", status_code=409)
        return api_id, api_hash, session_name

    async def credentials_ready(self) -> bool:
        """True bila kredensial Telegram sudah terisi (tanpa melempar galat)."""
        api_id, api_hash, _name = await self._load_credentials()
        return bool(api_id and api_id > 0 and api_hash)

    async def session_name(self) -> str:
        """Nama sesi yang sedang dipakai (dari setting, default bila kosong)."""
        _api_id, _api_hash, session_name = await self._load_credentials()
        return session_name or DEFAULT_SESSION_NAME

    def session_path(self, session_name: str) -> Path:
        """Lokasi berkas sesi Pyrogram untuk nama sesi tertentu."""
        return self._data_dir / f"{session_name}.session"

    def has_session_file(self, session_name: str) -> bool:
        """True bila berkas sesi sudah ada di direktori data."""
        return self.session_path(session_name).is_file()

    # ------------------------------------------------------------------- flow

    async def start(self, phone: str) -> LoginStart:
        """Kirim kode OTP ke `phone` lalu buka flow login baru."""
        normalized = normalize_phone(phone)
        api_id, api_hash, session_name = await self.credentials()

        async with self._lock:
            # Single-tenant: satu admin, satu alur. Flow lama dibuang agar tidak
            # ada dua klien Pyrogram menulis berkas sesi yang sama.
            await self._discard_all_flows()
            client = self._build_client(session_name, api_id, api_hash)
            try:
                await client.start()
                sent = await client.send_code(normalized)
            except Exception as exc:  # noqa: BLE001 - semua galat dipetakan ke kode
                await self._close_client(client)
                raise await self._record_failure(exc) from exc

            code_hash = str(getattr(sent, "phone_code_hash", "") or "")
            if not code_hash:
                await self._close_client(client)
                raise await self._record_failure(RuntimeError("phone_code_hash kosong"))
            self._remember_secret(code_hash)

            flow_id = await self._create_flow(normalized, code_hash)
            self._clients[flow_id] = client
            await self._set_account_status(ACCOUNT_LOGGED_OUT)

        log.info("Kode login Telegram dikirim (flow=%s).", flow_id)
        return LoginStart(flow_id=flow_id, next=NEXT_CODE)

    async def verify(self, flow_id: int, code: str) -> LoginResult:
        """Verifikasi kode OTP; mungkin ada langkah password 2FA berikutnya."""
        normalized = normalize_code(code)
        async with self._lock:
            flow = await self._load_flow(flow_id)
            self._remember_secret(normalized)
            client = await self._client_for_flow(flow)
            try:
                await client.sign_in(
                    flow.phone,
                    normalized,
                    phone_code_hash=flow.phone_code_hash,
                )
            except _SESSION_PASSWORD_EXCEPTIONS:
                await self._update_flow_status(flow_id, FLOW_AWAITING_PASSWORD)
                log.info("Login Telegram butuh password 2FA (flow=%s).", flow_id)
                return LoginResult(next=NEXT_PASSWORD)
            except Exception as exc:  # noqa: BLE001 - semua galat dipetakan ke kode
                raise await self._record_failure(exc) from exc

            await self._complete_login(client, flow)
            log.info("Login Telegram berhasil (flow=%s).", flow_id)
            return LoginResult(next=NEXT_DONE)

    async def submit_password(self, flow_id: int, password: str) -> None:
        """Kirim password 2FA untuk flow yang sedang menunggu (`awaiting_password`)."""
        if not password.strip():
            raise TelegramLoginError("password_invalid")
        async with self._lock:
            flow = await self._load_flow(flow_id)
            if flow.status != FLOW_AWAITING_PASSWORD:
                raise TelegramLoginError("flow_not_found", status_code=404)
            self._remember_secret(password)
            client = await self._client_for_flow(flow)
            try:
                await client.check_password(password)
            except Exception as exc:  # noqa: BLE001 - semua galat dipetakan ke kode
                raise await self._record_failure(exc) from exc

            await self._complete_login(client, flow)
            log.info("Login Telegram 2FA berhasil (flow=%s).", flow_id)

    async def cancel(self, flow_id: int) -> None:
        """Buang satu flow yang belum selesai."""
        async with self._lock:
            await self._load_flow(flow_id)
            client = self._clients.pop(flow_id, None)
            if client is not None:
                await self._close_client(client)
            await self._delete_flow(flow_id)
        log.info("Alur login Telegram dibatalkan (flow=%s).", flow_id)

    async def cleanup_expired(self) -> int:
        """Hapus `login_flow` kedaluwarsa; kembalikan jumlah yang dibuang."""
        async with self._lock:
            expired = await self._expired_flow_ids()
            for flow_id in expired:
                client = self._clients.pop(flow_id, None)
                if client is not None:
                    await self._close_client(client)
                await self._delete_flow(flow_id)
            if expired:
                log.info("%d alur login Telegram kedaluwarsa dibersihkan.", len(expired))
            return len(expired)

    async def cleanup_loop(self, interval: float = CLEANUP_INTERVAL_SEC) -> None:
        """Bersihkan flow kedaluwarsa secara berkala sampai task dibatalkan."""
        while True:
            try:
                await asyncio.sleep(interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - pembersih tidak boleh mematikan web
                log.exception("Gagal membersihkan alur login Telegram kedaluwarsa.")

    # ----------------------------------------------------------------- logout

    async def logout(self) -> dict[str, Any]:
        """Akhiri sesi di sisi Telegram lalu hapus seluruh berkas `*.session`."""
        remote_error: TelegramLoginError | None = None
        removed = 0
        async with self._lock:
            account = await self._load_account()
            session_name = str(account.session_name or await self.session_name())
            await self._discard_all_flows()

            remote_error = await self._remote_logout(session_name)
            removed = self._remove_session_files()
            await self._set_account_logged_out(session_name)
            if remote_error is not None:
                # Berkas lokal sudah hilang; catat saja kegagalan sisi Telegram.
                await self._set_last_error(remote_error.code)

        if remote_error is not None:
            log.warning(
                "Logout gagal di sisi Telegram (%s); berkas sesi lokal tetap dihapus.",
                remote_error.code,
            )
        log.info("Logout Telegram selesai (%d berkas sesi dihapus).", removed)
        return {
            "removed_session_files": removed,
            "remote_error": remote_error.code if remote_error else None,
        }

    # ----------------------------------------------------------------- status

    async def status(self) -> dict[str, Any]:
        """Ringkasan akun untuk UI (spesifikasi §6.4)."""
        account = await self._load_account()
        api_id, api_hash, session_name = await self._load_credentials()
        credentials_ready = bool(api_id and api_id > 0 and api_hash)

        status = str(account.status or ACCOUNT_NOT_CONFIGURED)
        # Q10: berkas sesi yang relevan adalah milik sesi yang dipakai saat login.
        # Bila `telegram_session_name` diganti, akun tetap `logged_in` tetapi ditandai
        # `session_mismatch` sehingga UI menawarkan login ulang.
        active_session = str(account.session_name or session_name)
        if status == ACCOUNT_LOGGED_IN and not self.has_session_file(active_session):
            # Sesi hilang di disk (mis. volume di-reset): jangan tampilkan "login".
            status = ACCOUNT_LOGGED_OUT
            await self._safely_set_logged_out()
        if not credentials_ready and status != ACCOUNT_LOGGED_IN:
            status = ACCOUNT_NOT_CONFIGURED

        user = None
        if account.tg_user_id is not None:
            user = {
                "id": account.tg_user_id,
                "username": account.tg_username,
                "first_name": account.tg_first_name,
            }

        return {
            "status": status,
            "phone": account.phone,
            "user": user,
            "last_error": account.last_error,
            "logged_in_at": (
                account.logged_in_at.isoformat() + "Z" if account.logged_in_at else None
            ),
            "credentials_configured": credentials_ready,
            "session_name": session_name,
            "session_mismatch": bool(
                status == ACCOUNT_LOGGED_IN and account.session_name not in (None, "", session_name)
            ),
        }

    # --------------------------------------------------------------- database

    async def _load_account(self) -> models.TelegramAccount:
        """Baris akun tunggal; dibuat dengan status default bila belum ada."""
        async with self._db.session() as session:
            row = await session.get(models.TelegramAccount, ACCOUNT_ROW_ID)
            if row is not None:
                return row
            row = models.TelegramAccount(id=ACCOUNT_ROW_ID, status=ACCOUNT_NOT_CONFIGURED)
            session.add(row)
        return row

    async def _update_account(self, **values: Any) -> None:
        """Tulis status akun dalam transaksi terpisah (tidak bergantung handler)."""
        async with self._db.session() as session:
            row = await session.get(models.TelegramAccount, ACCOUNT_ROW_ID)
            if row is None:
                row = models.TelegramAccount(
                    id=ACCOUNT_ROW_ID, status=ACCOUNT_NOT_CONFIGURED
                )
                session.add(row)
            for key, value in values.items():
                setattr(row, key, value)

    async def _set_account_status(self, status: str) -> None:
        await self._update_account(status=status, last_error=None)

    async def _set_account_logged_out(self, session_name: str) -> None:
        await self._update_account(
            status=ACCOUNT_LOGGED_OUT,
            tg_user_id=None,
            tg_username=None,
            tg_first_name=None,
            logged_in_at=None,
            session_name=session_name,
            last_error=None,
        )

    async def _set_last_error(self, error_code: str) -> None:
        """Simpan kode galat terakhir tanpa mengubah status akun."""
        async with self._db.session() as session:
            row = await session.get(models.TelegramAccount, ACCOUNT_ROW_ID)
            if row is None:
                session.add(
                    models.TelegramAccount(
                        id=ACCOUNT_ROW_ID,
                        status=ACCOUNT_NOT_CONFIGURED,
                        last_error=error_code,
                    )
                )
                return
            row.last_error = error_code

    async def _safely_set_logged_out(self) -> None:
        """Koreksi status saat endpoint status dipanggil (tidak boleh menggagalkan GET)."""
        try:
            await self._update_account(status=ACCOUNT_LOGGED_OUT, last_error=None)
        except Exception:  # noqa: BLE001 - koreksi status bersifat opsional
            log.debug("Gagal mengoreksi status akun menjadi logged_out.", exc_info=True)

    async def _create_flow(self, phone: str, phone_code_hash: str) -> int:
        now = utcnow()
        async with self._db.session() as session:
            flow = models.LoginFlow(
                phone=phone,
                phone_code_hash=phone_code_hash,
                status=FLOW_CODE_SENT,
                created_at=now,
                expires_at=now + self._flow_ttl,
            )
            session.add(flow)
            await session.flush()
            return int(flow.id)

    async def _load_flow(self, flow_id: int) -> models.LoginFlow:
        """Ambil flow yang masih hidup; galat bila tidak ada atau kedaluwarsa."""
        async with self._db.session() as session:
            flow = await session.get(models.LoginFlow, flow_id)
            if flow is None:
                raise TelegramLoginError("flow_not_found", status_code=404)
            if flow.expires_at <= utcnow():
                raise TelegramLoginError("flow_expired", status_code=410)
            return flow

    async def _update_flow_status(self, flow_id: int, status: str) -> None:
        async with self._db.session() as session:
            flow = await session.get(models.LoginFlow, flow_id)
            if flow is not None:
                flow.status = status

    async def _delete_flow(self, flow_id: int) -> None:
        async with self._db.session() as session:
            await session.execute(
                delete(models.LoginFlow).where(models.LoginFlow.id == flow_id)
            )

    async def _expired_flow_ids(self) -> list[int]:
        async with self._db.session() as session:
            rows = (
                (
                    await session.execute(
                        select(models.LoginFlow.id).where(
                            models.LoginFlow.expires_at <= utcnow()
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [int(row) for row in rows]

    async def _discard_all_flows(self) -> int:
        """Tutup semua klien flow dan hapus barisnya (single-tenant)."""
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await self._close_client(client)
        async with self._db.session() as session:
            result = await session.execute(delete(models.LoginFlow))
            return int(cast("CursorResult[Any]", result).rowcount or 0)

    # ------------------------------------------------------------------ klien

    def _build_client(self, session_name: str, api_id: int, api_hash: str) -> Any:
        """Buat klien login (workdir = direktori data, Q10)."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._remember_secret(api_hash)
        return self._client_factory(session_name, api_id, api_hash, self._data_dir)

    async def _client_for_flow(self, flow: models.LoginFlow) -> Any:
        """Klien untuk flow; bangun ulang bila proses web sempat restart."""
        flow_id = int(flow.id)
        client = self._clients.get(flow_id)
        if client is not None:
            return client

        api_id, api_hash, session_name = await self.credentials()
        client = self._build_client(session_name, api_id, api_hash)
        try:
            await client.start()
        except Exception as exc:  # noqa: BLE001 - semua galat dipetakan ke kode
            await self._close_client(client)
            raise await self._record_failure(exc) from exc
        self._clients[flow_id] = client
        return client

    @staticmethod
    async def _close_client(client: Any) -> None:
        """Tutup klien tanpa pernah menggagalkan alur login."""
        try:
            await client.stop()
        except Exception:  # noqa: BLE001 - klien yang gagal ditutup cukup dilupakan
            log.debug("Gagal menutup klien login Telegram.", exc_info=True)

    def _remove_session_files(self) -> int:
        """Hapus seluruh berkas `*.session*` di direktori data (satu akun aktif)."""
        removed = 0
        if not self._data_dir.is_dir():
            return 0
        for path in sorted(self._data_dir.glob("*.session*")):
            if not path.is_file():
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:  # berkas terkunci atau mount read-only: laporkan saja
                log.warning("Gagal menghapus berkas sesi '%s'.", path.name)
        return removed

    # ----------------------------------------------------------------- helpers

    async def _complete_login(self, client: Any, flow: models.LoginFlow) -> None:
        """Simpan hasil login ke `telegram_account`, lalu lepas berkas sesi."""
        session_name = await self.session_name()
        try:
            me = await client.get_me()
        finally:
            # Lepaskan berkas sesi agar runtime bisa membukanya nanti.
            await self._close_client(client)
            self._clients.pop(int(flow.id), None)

        await self._update_account(
            phone=flow.phone,
            tg_user_id=int(getattr(me, "id", 0) or 0),
            tg_username=getattr(me, "username", None),
            tg_first_name=getattr(me, "first_name", None),
            session_name=session_name,
            status=ACCOUNT_LOGGED_IN,
            last_error=None,
            logged_in_at=utcnow(),
        )
        await self._delete_flow(int(flow.id))

    async def _remote_logout(self, session_name: str) -> TelegramLoginError | None:
        """Panggil `log_out` bila kredensial ada; kegagalan tidak menghalangi lokal."""
        try:
            api_id, api_hash, _name = await self.credentials()
        except TelegramLoginError:
            log.info("Kredensial Telegram kosong; logout dijalankan secara lokal.")
            return None

        client = self._build_client(session_name, api_id, api_hash)
        try:
            await client.start()
            await client.log_out()
        except Exception as exc:  # noqa: BLE001 - kegagalan remote tidak fatal
            return map_exception(exc)
        finally:
            await self._close_client(client)
        return None

    async def _record_failure(self, exc: BaseException) -> TelegramLoginError:
        """Petakan exception, catat ke akun, lalu kembalikan untuk di-raise."""
        error = exc if isinstance(exc, TelegramLoginError) else map_exception(exc)
        if error.code in _ACCOUNT_BREAKING_CODES:
            await self._update_account(status=ACCOUNT_ERROR, last_error=error.code)
        else:
            await self._set_last_error(error.code)
        # Hanya kode stabil yang dicatat; pesan mentah bisa memuat detail sensitif.
        log.warning("Login Telegram gagal: %s", error.code)
        return error

    def _remember_secret(self, value: str | None) -> None:
        """Daftarkan nilai sensitif ke redactor (pengaman kedua terhadap log)."""
        if self._redactor is not None:
            self._redactor.add(value)