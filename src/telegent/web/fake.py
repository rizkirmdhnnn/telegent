"""Mode fake untuk pengujian end-to-end tanpa jaringan (tiket G1/H3).

Mode ini membuat runtime memakai **bot tiruan** dan layanan login Telegram memakai
**klien tiruan**, sehingga seluruh alur panel dapat diuji tanpa kredensial
Telegram/Gemini asli dan tanpa menyentuh jaringan.

Keamanan:

- hanya aktif bila variabel `TELEGENT_FAKE` bernilai **tepat** `1`; nilai lain
  (`true`, `yes`, `0`, kosong, ...) diabaikan dan menghasilkan peringatan;
- dibaca dari environment proses saja sehingga file `.env` yang dibaca panel sendiri
  tidak dapat mengaktifkannya;
- **ditolak bila direktori data sudah berisi data nyata** (berkas `*.session`
  Telegram atau kredensial tersimpan). Penjaga ini penting karena variabel
  environment bisa disuntikkan dari luar `.env` panel — misalnya lewat
  `env_file:` pada docker-compose, yang menyalin isi `.env` ke container apa adanya.
  Tanpa penjaga, sisa `TELEGENT_FAKE=1` dari pengujian bisa diam-diam menyalakan
  bot tiruan di produksi;
- selalu memunculkan peringatan mencolok saat aktif.

Yang **tidak** ditirukan: database, penyimpanan kredensial, dan autentikasi
admin. Mode fake bukan bypass keamanan — hanya mengganti sisi Telegram/Gemini.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

from pyrogram.errors import PhoneCodeInvalid

from telegent.app import TelegentApp
from telegent.web.bootstrap import FAKE_ENV
from telegent.web.db.base import Database
from telegent.config import Settings
from telegent.protocols import CallObserver
from telegent.telegram.call_session import END_REASON_AI, OUTCOME_ANSWERED

log = logging.getLogger("telegent.web.fake")

#: Nama variabel & nilai pengaktif berasal dari `bootstrap` (satu sumber kebenaran).
#: Diimpor, bukan diduplikasi, agar mengganti nama env tidak menyentuh dua modul.

#: Satu-satunya nilai yang dianggap benar-benar aktif.
FAKE_TRUTHY = "1"

#: Selang antar panggilan tiruan (detik); dapat diatur lewat env untuk e2e.
FAKE_CALL_INTERVAL_ENV = "TELEGENT_FAKE_CALL_INTERVAL"
DEFAULT_CALL_INTERVAL_SEC = 15.0

#: Jeda sebelum panggilan tiruan pertama, supaya halaman sempat selesai memuat.
FIRST_CALL_DELAY_SEC = 1.5

#: Kode OTP yang dianggap sah pada mode fake (dipakai skenario e2e).
FAKE_LOGIN_CODE = "12345"

#: Identitas akun tiruan yang dilaporkan ke panel.
FAKE_TG_ID = 424242
FAKE_TG_USERNAME = "telegent_fake"
FAKE_TG_FIRST_NAME = "Telegent (fake)"

#: Nomor telepon tiruan; pola tetap +62 agar lolos validasi `normalize_phone`.
FAKE_TG_PHONE = "+628000000000"


def fake_enabled() -> bool:
    """True HANYA bila `TELEGENT_FAKE=1` ada di environment proses.

    Nilai lain sengaja tidak dianggap aktif: salah ketik tidak boleh diam-diam
    mengubah produksi menjadi mode tiruan.
    """
    return os.environ.get(FAKE_ENV, "").strip() == FAKE_TRUTHY


#: Kunci setting yang menandakan ada kredensial sungguhan tersimpan.
_REAL_CREDENTIAL_KEYS = ("telegram_api_id", "gemini_api_key")


async def fake_blocked_reason(db: Database, data_dir: Path) -> str | None:
    """Alasan mode fake ditolak, atau `None` bila aman dipakai.

    Menolak kondisi yang akan membuat bot tiruan menimpa data produksi.
    """
    if not fake_enabled():
        return None

    for path in data_dir.glob("*.session*"):
        if path.is_file():
            return f"ditemukan berkas sesi Telegram nyata: {path.name}"

    from sqlalchemy import select

    from telegent.web.db import models

    async with db.session() as session:
        rows = (
            (
                await session.execute(
                    select(models.AppSetting.key, models.AppSetting.value).where(
                        models.AppSetting.key.in_(_REAL_CREDENTIAL_KEYS)
                    )
                )
            )
            .all()
        )
    for key, value in rows:
        if str(value).strip().strip('"'):
            return f"ditemukan kredensial tersimpan pada setting '{key}'"

    return None


def warn_if_fake_enabled() -> bool:
    """Beri peringatan mencolok bila mode fake aktif; kembalikan statusnya."""
    if not fake_enabled():
        return False
    log.warning(
        "MODE FAKE AKTIF - bot tiruan & klien Telegram tiruan dipakai. "
        "Tidak ada koneksi ke Telegram/Gemini; jangan pakai di produksi. "
        "Matikan dengan unset %s.",
        FAKE_ENV,
    )
    print(
        f"[WARNING] {FAKE_ENV}=1 - MODE FAKE AKTIF. "
        "Tidak ada koneksi Telegram/Gemini; jangan dipakai di produksi.",
        file=sys.stderr,
        flush=True,
    )
    return True


def fake_call_interval() -> float:
    """Selang antar panggilan tiruan (detik)."""
    raw = os.environ.get(FAKE_CALL_INTERVAL_ENV, "").strip()
    if not raw:
        return DEFAULT_CALL_INTERVAL_SEC
    try:
        value = float(raw)
    except ValueError:
        log.warning(
            "%s bukan angka; memakai default %ss.",
            FAKE_CALL_INTERVAL_ENV,
            DEFAULT_CALL_INTERVAL_SEC,
        )
        return DEFAULT_CALL_INTERVAL_SEC
    return value if value > 0 else DEFAULT_CALL_INTERVAL_SEC


# --------------------------------------------------------------- klien Telegram


class FakeTelegramClient:
    """Klien Pyrogram tiruan: hanya operasi yang dipakai `TelegramLoginService`.

    Menulis berkas `*.session` saat `start()` dipanggil, sama seperti Pyrogram
    aslinya, sehingga `RuntimeController` menemukan sesi hasil login tiruan.
    """

    def __init__(self, credentials: Any, workdir: Path | str, **_kwargs: Any) -> None:
        self.session_name = str(getattr(credentials, "session_name", credentials))
        self.api_id = getattr(credentials, "api_id", 0)
        self.api_hash = getattr(credentials, "api_hash", "")
        self.workdir = Path(workdir)
        self.started = False
        self.is_connected = False

    @property
    def _me(self) -> Any:
        return SimpleNamespace(
            id=FAKE_TG_ID,
            username=FAKE_TG_USERNAME,
            first_name=FAKE_TG_FIRST_NAME,
        )

    async def connect(self) -> bool:
        self.is_connected = True
        # Bila berkas sesi sudah ada di disk, sesi dianggap sudah terotorisasi.
        return (self.workdir / f"{self.session_name}.session").is_file()

    async def disconnect(self) -> None:
        self.is_connected = False
        self.started = False

    async def start(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / f"{self.session_name}.session").write_bytes(b"fake-session")
        self.started = True
        self.is_connected = True
        log.info("[fake] Klien Telegram tiruan start (sesi=%s).", self.session_name)

    async def stop(self) -> None:
        self.started = False
        self.is_connected = False

    async def send_code(self, phone: str) -> Any:
        log.info("[fake] Kode login dikirim ke %s.", mask_phone(phone))
        return SimpleNamespace(phone_code_hash=f"fake-code-hash-{FAKE_TG_ID}")

    async def sign_in(
        self, phone_number: str, _phone_code_hash: str, phone_code: str
    ) -> Any:
        if phone_code != FAKE_LOGIN_CODE:
            # Pengecualian yang SAMA dengan Pyrogram asli: `PhoneCodeInvalid` agar
            # panel benar-benar menguji pemetaan kode `code_invalid`, bukan
            # `telegram_error` generik yang tidak akan pernah terjadi di produksi.
            raise PhoneCodeInvalid
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / f"{self.session_name}.session").write_bytes(b"fake-session")
        self.started = True
        log.info("[fake] Login tiruan berhasil untuk %s.", mask_phone(phone_number))
        return self._me

    async def check_password(self, _password: str) -> Any:
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / f"{self.session_name}.session").write_bytes(b"fake-session")
        self.started = True
        return self._me

    async def get_me(self) -> Any:
        return self._me

    async def log_out(self) -> None:
        self.started = False
        self.is_connected = False


def fake_client_factory(credentials: Any, workdir: Path) -> Any:
    """Pabrik klien tiruan untuk `TelegramLoginService`."""
    return FakeTelegramClient(credentials, workdir)


def mask_phone(phone: str) -> str:
    """Sembunyikan sebagian nomor telepon agar tidak masuk log penuh.

    Nomor yang terlalu pendek disamarkan seluruhnya — menyisakan 4 digit terakhir
    dari angka pendek bisa jadi lebih informatif daripada tidak sama sekali.
    """
    if len(phone) <= 4:
        return "*" * len(phone)
    return f"***{phone[-4:]}"


# ------------------------------------------------------------------ bot tiruan


class FakeTelegentApp(TelegentApp):
    """`TelegentApp` tiruan: siklus hidup nyata, jaringan nol.

    Klien Pyrogram, ntgcalls, dan Gemini tidak pernah dibuat. Peristiwa panggilan
    disiarkan lewat `CallObserver` yang sama dengan produksi, sehingga UI
    pemantauan, SSE, dan penulisan database teruji lewat jalur aslinya.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        event_sink: Optional[Callable[[str, dict], None]] = None,
        call_observer: Optional[CallObserver] = None,
        tool_configs: Optional[dict[str, dict]] = None,
        **_kwargs: Any,
    ) -> None:
        super().__init__(
            settings,
            install_signal_handlers=False,
            event_sink=event_sink,
            tool_configs=tool_configs,
            call_observer=call_observer,
        )
        self._fake_task: Optional[asyncio.Task[None]] = None
        self._fake_call_seq = 0

    async def start(self) -> None:
        """Tandai berjalan lalu mulai menghasilkan panggilan tiruan."""
        self.loop = asyncio.get_running_loop()
        self.me = SimpleNamespace(
            id=FAKE_TG_ID,
            first_name=FAKE_TG_FIRST_NAME,
            username=FAKE_TG_USERNAME,
        )
        self._started = True
        self._log.info(
            "[fake] Telegent tiruan aktif (model=%s, maks %d bersamaan).",
            self.settings.gemini_model,
            self.settings.max_concurrent_calls,
        )
        self._emit("status", self.status_payload())
        self._fake_task = asyncio.create_task(
            self._fake_call_loop(), name="telegent-fake-calls"
        )

    async def shutdown(self) -> None:
        """Batalkan pengactoryuan panggilan; tidak ada klien native untuk ditutup."""
        task = self._fake_task
        if task is not None:
            self._fake_task = None
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._started = False
        self.app = None

    async def _fake_call_loop(self) -> None:
        """Terbitkan panggilan tiruan berulang sampai bot dihentikan."""
        interval = fake_call_interval()
        await asyncio.sleep(FIRST_CALL_DELAY_SEC)
        while not self._stop.is_set():
            try:
                self._simulate_call()
            except Exception:  # noqa: BLE001 - simulasi tidak boleh menjatuhkan bot
                log.exception("[fake] Gagal mensimulasikan panggilan.")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
            return

    def _simulate_call(self) -> None:
        """Satu panggilan tiruan lengkap: incoming, started, transkrip, tool, end."""
        self._fake_call_seq += 1
        call_id = 9_000_000 + self._fake_call_seq
        user_id = 5_000_000 + self._fake_call_seq
        observer = self._call_observer
        name = f"Pengguna {self._fake_call_seq}"

        if observer is not None:
            observer.call_incoming(call_id, user_id, user_display=name)
            observer.call_started(call_id, user_id)
            observer.session_event(
                call_id,
                "transcript",
                {"speaker": "caller", "text": "Halo, apakah masih ada?"},
            )
            observer.session_event(
                call_id,
                "transcript",
                {"speaker": "ai", "text": "Halo! Saya assistsen maya."},
            )
            observer.session_event(
                call_id,
                "tool_call",
                {
                    "name": "get_current_datetime",
                    "args": {},
                    "result": {"datetime": "2026-01-01T09:00:00+07:00"},
                    "status": "ok",
                    "duration_ms": 3,
                },
            )
            observer.call_ended(
                call_id,
                user_id,
                outcome=OUTCOME_ANSWERED,
                end_reason=END_REASON_AI,
                duration_sec=12,
            )

        # Status tetap "running" tanpa panggilan aktif (panggilan tiruan sudah
        # selesai di atas); event ini menjaga indicator UI tetap hidup.
        self._emit("status", self.status_payload())


def fake_app_factory(
    *,
    event_sink: Optional[Callable[[str, dict], None]],
    call_observer: Optional[CallObserver],
) -> Callable[[Settings], TelegentApp]:
    """Pabrik app tiruan yang sesuai tanda tangan `RuntimeController.app_factory`."""

    def factory(settings: Settings) -> TelegentApp:
        return FakeTelegentApp(
            settings,
            event_sink=event_sink,
            call_observer=call_observer,
        )

    return factory