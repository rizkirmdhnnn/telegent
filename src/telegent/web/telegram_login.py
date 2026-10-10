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
- **Lock hanya untuk state in-memory, bukan untuk I/O jaringan.** Satu
  `send_code` yang menggantung tidak boleh membekukan `logout`/`cancel`.
- **Tidak menyentuh jaringan saat diuji.** Klien dibuat lewat `ClientFactory`;
  tes meng-*stub* `Client` pada modul ini.

Akses database tidak ada di sini; semuanya lewat `TelegramStore`.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
from telegent.web.db import models
from telegent.web.db.base import Database
from telegent.web.log_stream import SecretRedactor
from telegent.web.telegram_errors import (
    ACCOUNT_BREAKING_CODES,
    TelegramLoginError,
    map_exception,
)
from telegent.web.settings_store import SettingsStore
from telegent.web.telegram_store import (
    ACCOUNT_ERROR,
    ACCOUNT_LOGGED_IN,
    ACCOUNT_LOGGED_OUT,
    ACCOUNT_NOT_CONFIGURED,
    FLOW_AWAITING_PASSWORD,
    FLOW_CODE_SENT,
    FlowExpired,
    FlowNotFound,
    TelegramStore,
)

log = logging.getLogger("telegent.web.telegram")

#: Umur maksimum satu alur login sebelum dibuang (±10 menit).
LOGIN_FLOW_TTL = timedelta(minutes=10)
#: Jeda antar pembersihan `login_flow` kedaluwarsa.
CLEANUP_INTERVAL_SEC = 300.0
#: Nama sesi cadangan bila setting `telegram_session_name` kosong.
DEFAULT_SESSION_NAME = "userbot_session"

# Nilai langkah berikutnya pada respons API.
NEXT_CODE = "code"
NEXT_PASSWORD = "password"
NEXT_DONE = "done"

_PHONE_NON_DIGITS = re.compile(r"[^0-9]")
_PHONE_FORMAT = re.compile(r"^\+?[0-9]{8,15}$")

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


@dataclass(frozen=True)
class TelegramCredentials:
    """Kredensial + nama sesi, satu nilai agar tidak tertukar saat diteruskan."""

    api_id: int
    api_hash: str
    session_name: str

    @property
    def ready(self) -> bool:
        return self.api_id > 0 and bool(self.api_hash)


#: Pabrik klien Pyrogram tak-terautentikasi: `(kredensial, workdir)` → klien.
ClientFactory = Callable[[TelegramCredentials, Path], Any]


def default_client_factory(credentials: TelegramCredentials, workdir: Path) -> Any:
    """Bangun klien Pyrogram tak-terautentikasi (tanpa nomor telepon)."""
    return Client(
        credentials.session_name,
        api_id=credentials.api_id,
        api_hash=credentials.api_hash,
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
        telegram_store: TelegramStore | None = None,
    ) -> None:
        self._store = telegram_store or TelegramStore(db, flow_ttl=flow_ttl)
        self._settings = store
        self._data_dir = Path(data_dir)
        self._redactor = redactor
        self._client_factory = client_factory or default_client_factory
        # Hanya melindungi peta klien & kunci per-flow; TIDAK dipakai saat I/O.
        self._clients_lock = asyncio.Lock()
        self._clients: dict[int, Any] = {}
        self._flow_locks: dict[int, asyncio.Lock] = {}

    # ------------------------------------------------------------- kredensial

    async def _load_credentials(self) -> TelegramCredentials | None:
        """Kredensial apa adanya dari store; `None` bila `api_id` belum terisi."""
        values = await self._settings.load_values()
        api_id = values.get("telegram_api_id")
        return TelegramCredentials(
            api_id=api_id if isinstance(api_id, int) else 0,
            api_hash=str(values.get("telegram_api_hash") or ""),
            session_name=str(
                values.get("telegram_session_name") or DEFAULT_SESSION_NAME
            ),
        )

    async def credentials(self) -> TelegramCredentials:
        """Kredensial siap pakai; galat `api_credentials_missing` bila belum lengkap."""
        credentials = await self._load_credentials()
        if credentials is None or not credentials.ready:
            raise TelegramLoginError("api_credentials_missing", status_code=409)
        return credentials

    async def credentials_ready(self) -> bool:
        """True bila kredensial Telegram sudah terisi (tanpa melempar galat)."""
        credentials = await self._load_credentials()
        return bool(credentials and credentials.ready)

    async def session_name(self) -> str:
        """Nama sesi yang sedang dipakai (dari setting, default bila kosong)."""
        credentials = await self._load_credentials()
        return (credentials.session_name if credentials else DEFAULT_SESSION_NAME) or (
            DEFAULT_SESSION_NAME
        )

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
        credentials = await self.credentials()

        # Keputusan produk: satu akun aktif, ganti akun = logout lalu login lagi.
        # Menimpanya lewat login baru berisiko membatalkan sesi yang sedang dipakai.
        account = await self._store.load_account()
        if account.status == ACCOUNT_LOGGED_IN:
            raise TelegramLoginError("already_logged_in", status_code=409)

        # Single-tenant: satu admin, satu alur. Flow lama dibuang agar tidak ada
        # dua klien Pyrogram menulis berkas sesi yang sama.
        await self._discard_all_flows()
        client = self._build_client(credentials)
        try:
            await client.start()
            sent = await client.send_code(normalized)
        except Exception as exc:  # noqa: BLE001 - semua galat dipetakan ke kode
            await self._close_client(client)
            raise await self._record_failure(exc) from exc

        # Redaksi diaktifkan lebih dulu: `phone_code_hash` ikut masuk query SQL,
        # dan driver SQLite menuliskan nilainya di log level DEBUG.
        self._remember_secret(str(sent.phone_code_hash))
        flow_id = await self._store.create_flow(normalized, str(sent.phone_code_hash))
        await self._remember_client(flow_id, client)
        log.info("Kode login Telegram dikirim (flow=%s).", flow_id)
        return LoginStart(flow_id=flow_id, next=NEXT_CODE)

    async def verify(self, flow_id: int, code: str) -> LoginResult:
        """Verifikasi kode OTP; mungkin ada langkah password 2FA berikutnya."""
        normalized = normalize_code(code)
        # Kunci per-flow: dua verify untuk flow sama tidak boleh saling menimpa,
        # namun tidak memblokir flow/logout yang lain.
        async with self._flow_lock(flow_id):
            flow = await self._load_flow(flow_id)
            self._remember_secret(normalized)
            client = await self._client_for_flow(flow)
            try:
                await client.sign_in(
                    flow.phone,
                    normalized,
                    phone_code_hash=flow.phone_code_hash,
                )
            except SessionPasswordNeeded:
                await self._store.set_flow_status(flow_id, FLOW_AWAITING_PASSWORD)
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
        async with self._flow_lock(flow_id):
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
        await self._load_flow(flow_id)
        client = await self._forget_client(flow_id)
        if client is not None:
            await self._close_client(client)
        await self._store.delete_flow(flow_id)
        log.info("Alur login Telegram dibatalkan (flow=%s).", flow_id)

    async def cleanup_expired(self) -> int:
        """Hapus `login_flow` kedaluwarsa; kembalikan jumlah yang dibuang."""
        expired = await self._store.expired_flow_ids()
        for flow_id in expired:
            client = await self._forget_client(flow_id)
            if client is not None:
                await self._close_client(client)
            await self._store.delete_flow(flow_id)
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
        account = await self._store.load_account()
        session_name = str(account.session_name or await self.session_name())
        if account.status != ACCOUNT_LOGGED_IN and not self.has_session_file(session_name):
            # Tidak ada yang bisa logout: jangan sentuh Telegram dan jangan
            # simpan `last_error` untuk kondisi yang memang belum pernah login.
            raise TelegramLoginError("account_not_logged_in", status_code=409)

        await self._discard_all_flows()
        remote_error = await self._remote_logout(session_name)
        removed = self._remove_session_files()
        await self._store.mark_logged_out(session_name)
        if remote_error is not None:
            # Berkas lokal sudah hilang; catat saja kegagalan sisi Telegram.
            await self._store.set_last_error(remote_error.code)

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
        """Ringkasan akun untuk UI (spesifikasi §6.4).

        **Hanya baca.** Status di database tidak dikoreksi di sini; koreksi
        terjadi saat admin logout atau login berikutnya.
        """
        account = await self._store.load_account()
        credentials = await self._load_credentials()
        credentials_ready = bool(credentials and credentials.ready)
        session_name = credentials.session_name if credentials else DEFAULT_SESSION_NAME

        status = str(account.status or ACCOUNT_NOT_CONFIGURED)
        # Q10: berkas sesi yang relevan adalah milik sesi yang dipakai saat login.
        # Bila `telegram_session_name` diganti, akun tetap `logged_in` tetapi ditandai
        # `session_mismatch` sehingga UI menawarkan logout lalu login ulang.
        active_session = str(account.session_name or session_name)
        if status == ACCOUNT_LOGGED_IN and not self.has_session_file(active_session):
            # Sesi hilang di disk (mis. volume di-reset): tampilkan "belum login"
            # tanpa menulis apa pun — endpoint ini bersifat baca.
            status = ACCOUNT_LOGGED_OUT
        if not credentials_ready and status != ACCOUNT_LOGGED_IN:
            status = ACCOUNT_NOT_CONFIGURED
        elif status == ACCOUNT_NOT_CONFIGURED and credentials_ready:
            # Kredensial sudah ada tetapi belum pernah ada percobaan login.
            status = ACCOUNT_LOGGED_OUT

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
                status == ACCOUNT_LOGGED_IN
                and account.session_name not in (None, "", session_name)
            ),
        }

    # ------------------------------------------------------------------ klien

    def _build_client(self, credentials: TelegramCredentials) -> Any:
        """Buat klien login (workdir = direktori data, Q10)."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._remember_secret(credentials.api_hash)
        return self._client_factory(credentials, self._data_dir)

    async def _client_for_flow(self, flow: models.LoginFlow) -> Any:
        """Klien untuk flow; bangun ulang bila proses web sempat restart."""
        flow_id = int(flow.id)
        async with self._clients_lock:
            client = self._clients.get(flow_id)
        if client is not None:
            return client

        credentials = await self.credentials()
        client = self._build_client(credentials)
        try:
            await client.start()
        except Exception as exc:  # noqa: BLE001 - semua galat dipetakan ke kode
            await self._close_client(client)
            raise await self._record_failure(exc) from exc
        await self._remember_client(flow_id, client)
        return client

    async def _remember_client(self, flow_id: int, client: Any) -> None:
        async with self._clients_lock:
            self._clients[flow_id] = client

    async def _forget_client(self, flow_id: int) -> Any:
        async with self._clients_lock:
            return self._clients.pop(flow_id, None)

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

    async def _discard_all_flows(self) -> None:
        """Tutup semua klien flow dan hapus barisnya (single-tenant)."""
        async with self._clients_lock:
            clients = list(self._clients.values())
            self._clients.clear()
            self._flow_locks.clear()
        for client in clients:
            await self._close_client(client)
        await self._store.delete_all_flows()

    # ----------------------------------------------------------------- helpers

    def _flow_lock(self, flow_id: int) -> asyncio.Lock:
        """Kunci per-flow; dibuat di luar `clients_lock` agar tidak mengunci I/O."""
        return self._flow_locks.setdefault(flow_id, asyncio.Lock())

    async def _load_flow(self, flow_id: int) -> models.LoginFlow:
        """Ambil flow; terjemahkan kegagalan store menjadi kode galat yang stabil."""
        try:
            return await self._store.load_flow(flow_id)
        except FlowExpired:
            raise TelegramLoginError("flow_expired", status_code=410) from None
        except FlowNotFound:
            raise TelegramLoginError("flow_not_found", status_code=404) from None

    async def _complete_login(self, client: Any, flow: models.LoginFlow) -> None:
        """Simpan hasil login ke akun, lalu lepas klien & alurnya.

        Pyrogram menulis berkas sesi **saat** otorisasi berhasil. Karena itu,
        kebuntuan pada `get_me()` tidak boleh meninggalkan alur menggantung:
        akun tetap ditandai login (profil boleh kosong) dan alur selalu dibuang.
        """
        session_name = await self.session_name()
        me: Any = None
        try:
            me = await client.get_me()
        except Exception as exc:  # noqa: BLE001 - profil saja yang gagal diambil
            log.warning(
                "Gagal mengambil profil Telegram setelah login (flow=%s): %s",
                int(flow.id),
                exc.__class__.__name__,
            )
        finally:
            await self._close_client(client)
            await self._forget_client(int(flow.id))

        await self._store.mark_logged_in(
            phone=flow.phone,
            session_name=session_name,
            user_id=int(getattr(me, "id", 0) or 0) if me is not None else None,
            username=getattr(me, "username", None),
            first_name=getattr(me, "first_name", None),
        )
        await self._store.delete_flow(int(flow.id))

    async def _remote_logout(self, session_name: str) -> TelegramLoginError | None:
        """Panggil `log_out` bila kredensial ada; kegagalan tidak menghalangi lokal."""
        try:
            credentials = await self.credentials()
        except TelegramLoginError:
            log.info("Kredensial Telegram kosong; logout dijalankan secara lokal.")
            return None

        client = self._build_client(credentials)
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
        if error.code in ACCOUNT_BREAKING_CODES:
            await self._store.update_account(status=ACCOUNT_ERROR, last_error=error.code)
        else:
            await self._store.set_last_error(error.code)
        # Hanya kode stabil yang dicatat; pesan mentah bisa memuat detail sensitif.
        log.warning("Login Telegram gagal: %s", error.code)
        return error

    def _remember_secret(self, value: str | None) -> None:
        """Daftarkan nilai sensitif ke redactor (pengaman kedua terhadap log)."""
        if self._redactor is not None:
            self._redactor.add(value)