"""Kontrol runtime bot dari panel web: start, stop, restart, dan status.

`RuntimeController` membungkus `TelegentApp` sehingga dapat dijalankan, dihentikan,
dan di-restart **tanpa mematikan proses web**. Semua operasi diserialisasi dengan
seatuang agar aman dari klik ganda.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from telegent.app import EventSink, TelegentApp
from telegent.config import Settings
from telegent.protocols import CallObserver
from telegent.telegram.call_session import END_REASON_PANEL, CallSession
from telegent.web.db.base import utcnow
from telegent.web.settings_registry import REGISTRY, ApplyMode
from telegent.web.settings_store import NotConfigured, SettingsStore

log = logging.getLogger("telegent.web.runtime")

STOP_TIMEOUT_SEC = 20.0

#: Batas tunggu graceful drain (F1): sebelum stop/restart, panggilan aktif
#: diminta pamitan lebih dulu; yang masih tersisa setelah batas ini dipaksa tutup.
DRAIN_TIMEOUT_SEC = 10.0

#: Selang jeda saat menunggu sesi aktif benar-benar berakhir.
DRAIN_POLL_SEC = 0.2

#: Pabrik TelegentApp (di-override pada pengujian dengan fake).
AppFactory = Callable[[Settings], TelegentApp]

#: Pemuat konfigurasi tool dari database (kembalikan `{nama: config}`).
ToolConfigProvider = Callable[[], Awaitable[dict[str, dict[str, Any]]]]


class RuntimeState(str, Enum):
    """Status runtime yang ditampilkan ke UI."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    NOT_CONFIGURED = "not_configured"
    NEEDS_LOGIN = "needs_login"
    ERROR = "error"


@dataclass
class RuntimeStatus:
    """Ringkasan status runtime (siap dikirim sebagai JSON)."""

    state: RuntimeState = RuntimeState.STOPPED
    running: bool = False
    model: str | None = None
    active_calls: int = 0
    logged_in_user: dict[str, Any] | None = None
    last_error: str | None = None
    since: str | None = None
    pending_restart: list[str] = field(default_factory=list)
    #: Jumlah panggilan yang diakhiri graceful pada drain terakhir (spec §6.5).
    last_drained: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


class RuntimeController:
    """Mengelola satu instance `TelegentApp` di dalam proses web."""

    def __init__(
        self,
        store: SettingsStore,
        *,
        app_factory: AppFactory | None = None,
        event_sink: EventSink | None = None,
        session_dir: Path | None = None,
        tool_config_provider: ToolConfigProvider | None = None,
        call_observer: CallObserver | None = None,
        drain_timeout: float = DRAIN_TIMEOUT_SEC,
    ) -> None:
        self._store = store
        self._event_sink = event_sink
        self._tool_config_provider = tool_config_provider
        self._tool_configs: dict[str, dict[str, Any]] = {}
        self._app_factory: AppFactory = app_factory or (
            lambda settings: TelegentApp(
                settings,
                install_signal_handlers=False,
                event_sink=event_sink,
                tool_configs=self._tool_configs,
                call_observer=call_observer,
            )
        )
        self._session_dir = session_dir
        self._app: Optional[TelegentApp] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._state = RuntimeState.STOPPED
        self._last_error: str | None = None
        self._since: str | None = None
        self._settings: Optional[Settings] = None
        self._pending_restart: list[str] = []
        self._last_drained: int = 0
        self._drain_timeout = drain_timeout
        self._stop_initiated = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- properties

    @property
    def app(self) -> Optional[TelegentApp]:
        return self._app

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def settings(self) -> Optional[Settings]:
        return self._settings

    @property
    def tool_configs(self) -> dict[str, dict[str, Any]]:
        """Konfigurasi tool yang akan dipakai saat bot dijalankan."""
        return dict(self._tool_configs)

    # ----------------------------------------------------------------- panggilan

    def active_sessions(self) -> list[CallSession]:
        """Sesi panggilan yang sedang berjalan; kosong saat bot tidak hidup.

        Bot yang berhenti tidak punya sesi: endpoint pemantauan mengembalikan
        daftar kosong, bukan galat.
        """
        if self._app is None:
            return []
        return self._app.active_sessions()

    def find_session_by_call_id(self, tg_call_id: int) -> CallSession | None:
        """Sesi aktif dengan `tg_call_id` tertentu (atau `None`)."""
        return next(
            (s for s in self.active_sessions() if s.call_id == tg_call_id),
            None,
        )

    # ------------------------------------------------------------------ status

    def publish(self, event: str, payload: dict[str, Any]) -> None:
        """Terbitkan event ke panel (mis. `runtime.error`).

        Kegagalan tidak pernah dilempar: pemantau tidak boleh menjatuhkan bot.
        """
        if self._event_sink is None:
            return
        try:
            self._event_sink(event, payload)
        except Exception:  # noqa: BLE001 - pemantau tidak boleh mengganggu bot
            log.debug("Gagal menerbitkan event '%s'.", event, exc_info=True)

    def _publish_status(self) -> None:
        self.publish("status", self.status().to_dict())

    def status(self) -> RuntimeStatus:
        """Status saat ini (aman dipanggil kapan saja)."""
        payload: dict[str, Any] = {}
        if self._app is not None:
            try:
                payload = self._app.status_payload()
            except Exception:  # noqa: BLE001 - jangan pernah gagalkan endpoint status
                payload = {}

        return RuntimeStatus(
            state=self._state,
            running=bool(self._state is RuntimeState.RUNNING and payload.get("running")),
            model=payload.get("model") or (self._settings.gemini_model if self._settings else None),
            active_calls=int(payload.get("active_calls", 0)),
            logged_in_user=payload.get("logged_in_user"),
            last_error=self._last_error,
            since=self._since,
            pending_restart=list(self._pending_restart),
            last_drained=self._last_drained,
        )

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> RuntimeStatus:
        """Jalankan bot bila konfigurasi & sesi Telegram siap."""
        async with self._lock:
            if self._state is RuntimeState.RUNNING:
                return self.status()

            self._state = RuntimeState.STARTING
            self._last_error = None
            self._publish_status()

            try:
                settings = await self._store.build_settings()
            except NotConfigured as exc:
                self._state = RuntimeState.NOT_CONFIGURED
                self._last_error = str(exc)
                log.info("Runtime belum dijalankan: konfigurasi kurang (%s).", exc)
                return self.status()

            if not self._is_logged_in(settings):
                self._state = RuntimeState.NEEDS_LOGIN
                self._last_error = "Belum ada sesi Telegram. Silakan login di halaman Telegram."
                log.info("Runtime belum dijalankan: sesi Telegram belum ada.")
                return self.status()

            app = self._app_factory(settings)
            try:
                await self._load_tool_configs()
                await app.start()
            except Exception as exc:  # noqa: BLE001 - kegagalan bot tidak mematikan web
                self._state = RuntimeState.ERROR
                self._last_error = self._safe_error(exc)
                log.exception("Gagal menjalankan bot.")
                self.publish("runtime.error", {"message": self._last_error})
                return self.status()

            self._app = app
            self._settings = settings
            self._state = RuntimeState.RUNNING
            self._since = utcnow().isoformat() + "Z"
            self._task = asyncio.create_task(self._supervise(app), name="telegent-runtime")
            self._pending_restart = await self._store.restart_keys_pending(settings)
            log.info("Runtime berjalan (model=%s).", settings.gemini_model)
            self._publish_status()
            return self.status()

    async def _supervise(self, app: TelegentApp) -> None:
        """Tunggu aplikasi berhenti, lalu bersihkan state internal."""
        try:
            await app.wait_stopped()
        except asyncio.CancelledError:  # pragma: no cover - hanya saat shutdown
            raise
        finally:
            await app.shutdown()
            if self._app is app:
                self._app = None
                self._task = None
                self._state = RuntimeState.STOPPED
                self._since = None
                # Kalau berhenti karena permintaan `stop()`, status sudah disiarkan
                # di sana; mengulang di sini membuat event dobel.
                if not self._stop_initiated:
                    self._publish_status()

    @property
    def last_drained(self) -> int:
        """Jumlah panggilan aktif yang diakhiri graceful pada stop/restart terakhir."""
        return self._last_drained

    async def drain_active_calls(self, timeout: float = DRAIN_TIMEOUT_SEC) -> int:
        """Akhiri panggilan aktif secara graceful; kembalikan jumlah yang diakhiri.

        Sesi diberi waktu pamitan (`schedule_hangup`) alih-alih langsung ditutup,
        sehingga penelpon tidak mendengar pemutusan mendadak. Sesi yang masih hidup
        setelah `timeout` dipaksa `close()` — drain tidak boleh menggantungkan
        proses web. Mengembalikan jumlah sesi yang masih hidup saat drain dimulai.
        """
        sessions = self.active_sessions()
        self._last_drained = len(sessions)
        if not sessions:
            return 0

        for session in sessions:
            try:
                session.schedule_hangup(reason=END_REASON_PANEL)
            except Exception:  # noqa: BLE001 - satu sesi gagal tidak boleh membatalkan drain
                log.warning("Gagal menjadwalkan hangup sesi %s.", session.user_id, exc_info=True)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            still_open = [
                session for session in sessions if self._session_alive(session)
            ]
            if not still_open:
                break
            if loop.time() >= deadline:
                log.warning(
                    "%d panggilan aktif tidak selesai dalam %ss; dipaksa ditutup.",
                    len(still_open),
                    timeout,
                )
                for session in still_open:
                    try:
                        await session.close()
                    except Exception:  # noqa: BLE001 - closure paksa tetap tidak boleh menggagalkan stop
                        log.warning(
                            "Gagal menutup sesi %s.", session.user_id, exc_info=True
                        )
                break
            await asyncio.sleep(DRAIN_POLL_SEC)
        return self._last_drained

    def _session_alive(self, session: CallSession) -> bool:
        """True bila sesi masih terdaftar pada aplikasi yang sedang berjalan.

        Sesi yang sudah selesai akan dibuang dari `app.sessions` oleh callback
        `on_stop`; itulah sinyal drain bahwa panggilan sudah benar-benar berakhir.
        """
        if self._app is None:
            return False
        return any(existing is session for existing in self._app.active_sessions())

    async def stop(self) -> RuntimeStatus:
        """Hentikan bot: drain panggilan aktif lebih dulu, lalu tutup.

        Seluruh urutan ini berada di dalam `_lock`. Sebelumnya drain berjalan
        **luar** lock sehingga `start()` bisa membangun app baru di tengah
        jendela drain, lalu `stop()` mematikan bot yang baru saja dinyalakan.
        """
        async with self._lock:
            app = self._app
            if app is None:
                if self._state in (
                    RuntimeState.NOT_CONFIGURED,
                    RuntimeState.NEEDS_LOGIN,
                    RuntimeState.ERROR,
                ):
                    self._state = RuntimeState.STOPPED
                return self.status()

            # Status disiarkan lebih dulu: UI harus tahu transisi dimulai, dan
            # nilai ini juga dipakai sebagai `before` pada audit.
            self._state = RuntimeState.STOPPING
            self._publish_status()

            # Drain hanya bermakna bila `_app` ada; `drain_active_calls` sudah
            # menulis `_last_drained` sehingga tidak perlu di-set lagi di sini.
            await self.drain_active_calls(self._drain_timeout)

            self._stop_initiated = True
            try:
                await app.stop()
                task = self._task
                if task is not None:
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(task), timeout=STOP_TIMEOUT_SEC
                        )
                    except asyncio.TimeoutError:
                        log.warning(
                            "Runtime tidak berhenti dalam %ss; dipaksa.", STOP_TIMEOUT_SEC
                        )
                        task.cancel()
                        await app.shutdown()
                        self._app = None
                        self._task = None
            finally:
                self._stop_initiated = False

            self._state = RuntimeState.STOPPED
            self._since = None
            self._publish_status()
            return self.status()

    async def restart(self) -> RuntimeStatus:
        """Berhenti lalu jalankan kembali dengan konfigurasi terbaru."""
        await self.stop()
        async with self._lock:
            self._state = RuntimeState.STOPPED
            self._app = None
            self._task = None
        return await self.start()

    async def shutdown(self) -> None:
        """Dipanggil saat proses web berhenti."""
        try:
            await self.stop()
        except Exception:  # noqa: BLE001 - jangan gagalkan shutdown web
            log.exception("Gagal menghentikan runtime saat shutdown web.")

    # -------------------------------------------------------------- konfigurasi

    async def refresh_settings(self) -> RuntimeStatus:
        """Terapkan konfigurasi terbaru (live-apply) bila bot sedang jalan.

        Hanya setting kelas `hot` yang langsung diterapkan; nilai yang ditandai
        `restart` tetap memakai konfigurasi lama sampai bot di-restart.
        """
        self._pending_restart = await self._store.restart_keys_pending(self._settings)

        try:
            stored = await self._store.build_settings()
        except NotConfigured:
            return self.status()

        if self._app is not None and self._state is RuntimeState.RUNNING:
            effective = self._effective_settings(stored)
            self._app.set_settings(effective)
            self._settings = effective
            log.info("Konfigurasi hot diterapkan ke runtime.")
        self._publish_status()
        return self.status()

    def _effective_settings(self, stored: Settings) -> Settings:
        """Nilai hot terbaru + nilai lama untuk setting yang perlu restart."""
        if self._settings is None:
            return stored
        data = stored.model_dump()
        for key, spec in REGISTRY.items():
            if spec.apply is ApplyMode.RESTART and key in Settings.model_fields:
                data[key] = getattr(self._settings, key)
        return Settings.model_validate(data)

    async def apply_pending(self) -> RuntimeStatus:
        """Restart bila ada perubahan yang menunggu; jika tidak, refresh saja."""
        if not await self._store.restart_keys_pending(self._settings):
            return await self.refresh_settings()
        return await self.restart()

    # ------------------------------------------------------------------- tools

    async def _load_tool_configs(self) -> None:
        """Muat konfigurasi tool tersimpan agar berlaku saat runtime dibangun.

        Nilai di database menang, tetapi entri yang baru saja disimpan lewat
        panel (belum tersinkron ke DB pada kasus ini) tetap dipertahankan.
        """
        if self._tool_config_provider is None:
            return
        try:
            loaded = await self._tool_config_provider()
        except Exception:  # noqa: BLE001 - konfigurasi tool tidak boleh menghalangi start
            log.exception("Gagal memuat konfigurasi tool; memakai nilai di memori.")
            return
        self._tool_configs = {**self._tool_configs, **loaded}

    async def apply_tool_config(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Terapkan perubahan tool ke bot yang hidup **dan** ke start berikutnya.

        Nilai disimpan pada controller karena konfigurasi di database sudah
        tersimpan; hidrolasi ulang dilakukan setiap `start()`.
        """
        if config is not None:
            self._tool_configs[name] = config
        elif name not in self._tool_configs:
            self._tool_configs[name] = {}

        if self._app is None or self._state is not RuntimeState.RUNNING:
            # Bot mati: cukup simpan; `start()` berikutnya akan memuatnya.
            return
        try:
            self._app.apply_tool_config(name, enabled=enabled, config=config)
        except (KeyError, ValueError) as exc:
            # Nilai tak valid sudah ditolak router; Reaching here berarti data basi.
            log.warning("Gagal menerapkan konfigurasi tool '%s': %s", name, exc)

    # ------------------------------------------------------------------ utilitas

    def _is_logged_in(self, settings: Settings) -> bool:
        """True bila berkas sesi Telegram tersedia."""
        directory = self._session_dir
        if directory is None:
            directory = Path(settings.session_dir)
        name = settings.telegram_session_name
        return (directory / f"{name}.session").exists()

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        """Ubah exception menjadi pesan singkat tanpa membocorkan secret."""
        message = str(exc).strip() or exc.__class__.__name__
        return message[:300]