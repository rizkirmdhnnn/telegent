"""Orkestrasi Telegent: klien Telegram, media ntgcalls, dan dispatch panggilan."""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager, suppress
from typing import Any, AsyncIterator, Callable, Optional

import ntgcalls
from google import genai
from google.genai import types as genai_types
from pyrogram import Client
from pyrogram.handlers import RawUpdateHandler
from pyrogram.raw import functions, types

from telegent.ai.live_session import GeminiLiveSession
from telegent.ai.tools.builtin import default_tools
from telegent.ai.tools.registry import ToolRegistry
from telegent.config import Settings
from telegent.logging_setup import call_logger, get_logger
from telegent.protocols import CallObserver
from telegent.rate_limit import CallRateLimiter
from telegent.telegram.call_session import (
    END_REASON_AI,
    END_REASON_CALLER,
    END_REASON_ERROR,
    END_REASON_REJECTED,
    OUTCOME_ANSWERED,
    OUTCOME_ERROR,
    CallSession,
    SessionState,
)
from telegent.telegram.media import NtgAudioSink, external_audio_media
from telegent.telegram.signaling import SignalingService, to_ntg_rtc_server, to_tg_protocol

#: Pemantau opsional untuk panel web: (nama_event, payload) -> None.
EventSink = Callable[[str, dict], None]


class SessionNotAuthorized(RuntimeError):
    """Berkas sesi Telegram ada, tetapi belum terotorisasi.

    Dilempar alih-alih membiarkan Pyrogram meminta nomor telepon di stdin:
    di panel web tidak ada terminal, dan `Client.start()` akan memanggil
    `authorize()` yang membaca `stdin` lalu menggantung / `EOFError`.
    """


class TelegentApp:
    """Aplikasi utama: menerima panggilan Telegram dan menjalankan sesi AI per panggilan."""

    def __init__(
        self,
        settings: Settings,
        *,
        install_signal_handlers: bool = True,
        event_sink: Optional[EventSink] = None,
        tool_configs: Optional[dict[str, dict]] = None,
        call_observer: Optional[CallObserver] = None,
    ) -> None:
        self.settings = settings
        self._log = get_logger("telegent.app")
        self.app: Optional[Client] = None
        self.ntg: Optional[ntgcalls.NTgCalls] = None
        self.gemini_client: Optional[genai.Client] = None
        self.signaling: Optional[SignalingService] = None
        self.me: Optional[object] = None
        self.tools = ToolRegistry()
        for spec in default_tools():
            self.tools.register(spec)
        # Konfigurasi tool dari panel web (zona waktu, status aktif, dll).
        self.tools.apply_configs(tool_configs or {})
        self.sessions: dict[int, CallSession] = {}
        self.rate_limiter = CallRateLimiter(
            settings.max_calls_per_window, settings.call_window_seconds
        )
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = asyncio.Event()
        self._install_signal_handlers_on_start = install_signal_handlers
        self._event_sink = event_sink
        self._call_observer = call_observer
        self._started = False

    # -------------------------------------------------------------- properties

    @property
    def is_running(self) -> bool:
        """True bila klien Telegram sudah start dan belum dihentikan."""
        return self._started and not self._stop.is_set()

    @property
    def lifecycle_state(self) -> str:
        """Status siklus hidup sederhana untuk UI (spesifikasi §7 `state`)."""
        if self._started and not self._stop.is_set():
            return "running"
        if self._started:
            return "stopping"
        return "stopped"

    @property
    def active_call_count(self) -> int:
        return len(self.sessions)

    def active_sessions(self) -> list["CallSession"]:
        """Sesi panggilan yang sedang berjalan (untuk panel pemantau).

        Salinan daftar, bukan objek sesi itu sendiri: pemanggil di luar loop
        hanya boleh membaca, bukan mengubah state sesi.
        """
        return list(self.sessions.values())

    # ---------------------------------------------------------------- lifecycle

    def set_settings(self, settings: Settings) -> None:
        """Ganti konfigurasi untuk panggilan berikutnya (live-apply).

        Panggilan yang sedang berjalan tetap memakai konfigurasi lamanya.
        """
        self.settings = settings
        self.rate_limiter = CallRateLimiter(
            settings.max_calls_per_window, settings.call_window_seconds
        )

    def apply_tool_config(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        config: dict | None = None,
    ) -> None:
        """Terapkan perubahan tool pada registry yang hidup."""
        self.tools.configure(name, enabled=enabled, config=config)

    def _emit(self, event: str, payload: dict) -> None:
        """Terbitkan event ke pemantau web (diabaikan bila tidak ada pemantau)."""
        if self._event_sink is None:
            return
        try:
            self._event_sink(event, payload)
        except Exception:  # noqa: BLE001 - pemantau tidak boleh mengganggu bot
            self._log.debug("Gagal menerbitkan event '%s'.", event, exc_info=True)

    def _emit_call(self, event: str, payload: dict) -> None:
        """Terbitkan event `call.*` **hanya bila tidak ada `CallObserver`**.

        `CallRecorder` adalah penerbit utama karena ia tahu `record_id` sehingga
        kejadian tak terkirim dua kali ke bus. Tanpa observer, `_emit` tetap
        menjadi jalan keluar (runtime tanpa panel, atau pengujian).
        """
        if self._call_observer is not None:
            return
        self._emit(event, payload)

    def _observe_call(self, method: str, tg_call_id: int, user_id: int, **kwargs: object) -> None:
        """Teruskan siklus hidup panggilan ke `CallObserver` (penyimpan E1).

        Implementasi pemantau wajib sinkron & non-memblokir; galat ditelan
        agar kegagalan penyimpanan tidak pernah menjatuhkan panggilan.
        """
        observer = self._call_observer
        if observer is None:
            return
        try:
            getattr(observer, method)(tg_call_id, user_id, **kwargs)
        except Exception:  # noqa: BLE001 - kegagalan monitor tidak boleh mengganggu bot
            self._log.debug("Gagal notifying observer '%s'.", method, exc_info=True)

    async def start(self) -> None:
        """Bangun klien dan mulai menerima panggilan.

        Melempar exception bila gagal (kredensial/sesi tidak valid).
        """
        if self._started:
            return

        self.loop = asyncio.get_running_loop()
        self.app = Client(
            self.settings.telegram_session_name,
            api_id=self.settings.telegram_api_id,
            api_hash=self.settings.telegram_api_hash,
            workdir=str(self.settings.session_workdir),
        )
        self.ntg = ntgcalls.NTgCalls()
        self.gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
        self.signaling = SignalingService(self.app, self.loop, self._log)

        self._setup_ntg_callbacks()
        self._setup_handlers()
        if self._install_signal_handlers_on_start:
            self._install_signal_handlers()

        # Replika `Client.start()` tanpa `authorize()`: bila sesi belum
        # terotorisasi kita berhenti dengan galat yang jelas, bukan prompt.
        me = await self._start_client()
        self.me = me
        self._started = True
        self._log.info(
            "Login sebagai: %s (@%s, id=%s)", me.first_name, me.username or "-", me.id
        )
        self._log.info(
            "Telegent aktif. Menunggu panggilan (maks %d bersamaan, model=%s).",
            self.settings.max_concurrent_calls,
            self.settings.gemini_model,
        )
        self._emit("status", self.status_payload())

    async def _start_client(self) -> Any:
        """Hubungkan klien Pyrogram; gagal cepat bila sesi belum terotorisasi.

        Mengembalikan objek user Telegram hasil autorisasi yang sudah ada.
        """
        client = self.app
        if client is None:  # pragma: no cover - dijamin oleh start()
            raise RuntimeError("Klien Telegram belum dibuat.")

        authorized = bool(await client.connect())
        if not authorized:
            await client.disconnect()
            raise SessionNotAuthorized(
                "Berkas sesi Telegram belum terotorisasi. "
                "Silakan login lewat halaman Telegram pada panel."
            )

        try:
            await client.invoke(functions.updates.GetState())
            me = await client.get_me()
            await client.initialize()
        except BaseException:
            # `disconnect()` menolak klien yang sudah terputus; abaikan saja.
            with suppress(Exception):
                await client.disconnect()
            raise
        return me

    async def wait_stopped(self) -> None:
        """Tunggu sampai diminta berhenti (SIGINT/SIGTERM atau `stop()`)."""
        await self._stop.wait()

    async def stop(self) -> None:
        """Minta aplikasi berhenti; boleh dipanggil berulang."""
        if self._stop.is_set():
            return
        self._stop.set()
        # Spec §7: UI harus tahu bot berhenti, bukan hanya tahu saat start.
        self._emit("status", self.status_payload())

    async def shutdown(self) -> None:
        """Tutup sesi & klien (idempoten)."""
        if not self._started and self.app is None:
            return
        self._log.info("Mematikan; menutup %d sesi aktif.", len(self.sessions))
        for session in list(self.sessions.values()):
            await session.close()
        self.sessions.clear()
        if self.app is not None:
            try:
                await self.app.stop()
            except Exception as exc:  # noqa: BLE001
                self._log.warning("Gagal menutup klien Telegram: %s", exc)
        self._started = False
        self.app = None

    def status_payload(self) -> dict:
        """Ringkasan status untuk panel web (spesifikasi §7)."""
        me = self.me
        return {
            "running": self.is_running,
            "state": self.lifecycle_state,
            "active_calls": self.active_call_count,
            "model": self.settings.gemini_model,
            "max_concurrent_calls": self.settings.max_concurrent_calls,
            "logged_in_user": (
                {
                    "id": getattr(me, "id", None),
                    "first_name": getattr(me, "first_name", None),
                    "username": getattr(me, "username", None),
                }
                if me is not None
                else None
            ),
        }

    async def serve(self) -> None:
        """Jalankan bot sampai dihentikan (start → wait → shutdown)."""
        await self.start()
        try:
            await self._stop.wait()
        finally:
            await self.shutdown()

    async def run(self) -> None:
        """Entry point untuk mode headless (`telegent --no-web`)."""
        await self.serve()

    def _install_signal_handlers(self) -> None:
        assert self.loop is not None
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(sig, self._stop.set)
            except (NotImplementedError, RuntimeError):
                pass

    # ---------------------------------------------------------------- callbacks
    def _setup_ntg_callbacks(self) -> None:
        ntg = self.ntg
        signaling = self.signaling
        loop = self.loop
        if ntg is None or signaling is None or loop is None:
            return

        def on_signaling_data(user_id: int, data: bytes) -> None:
            # Callback native (thread ntgcalls): hanya dispatch ke loop utama,
            # jangan sentuh state sesi dari thread ini.
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._on_signaling_data, user_id, data)

        def on_connection_change(user_id: int, info: ntgcalls.ConnectionInfo) -> None:
            state_name = str(info.state).split(".")[-1]
            kind_name = str(info.kind).split(".")[-1]
            self._log.info("[Media] user=%s state=%s kind=%s", user_id, state_name, kind_name)

        def on_frames(user_id: int, mode, _device, frames) -> None:
            if mode != ntgcalls.StreamMode.PLAYBACK:
                return
            raw = bytearray()
            for frame in frames:
                if frame.data:
                    raw.extend(frame.data)
            if raw and not loop.is_closed():
                loop.call_soon_threadsafe(self._deliver_incoming_pcm, user_id, bytes(raw))

        ntg.on_signaling_data(on_signaling_data)
        ntg.on_connection_change(on_connection_change)
        ntg.on_frames(on_frames)

    # --- Handler yang berjalan di event loop utama (state sesi aman) ---
    def _on_signaling_data(self, user_id: int, data: bytes) -> None:
        session = self.sessions.get(user_id)
        if session is None or self.signaling is None:
            return
        if not session.signaling_ready:
            if len(session.pending_signaling) < 512:
                session.pending_signaling.append(data)
            return
        self.signaling.dispatch(session, data)

    def _deliver_incoming_pcm(self, user_id: int, raw: bytes) -> None:
        session = self.sessions.get(user_id)
        if session is not None:
            session.handle_incoming_telegram_pcm(raw)

    def _setup_handlers(self) -> None:
        assert self.app is not None

        async def handle_raw_update(_client, update, _users, _chats) -> None:
            if isinstance(update, types.UpdatePhoneCall):
                call = update.phone_call
                self._log.info("[PhoneCall] %s (id=%s)", type(call).__name__, getattr(call, "id", "?"))
                if isinstance(call, types.PhoneCallRequested):
                    await self._handle_call_requested(call)
                elif isinstance(call, types.PhoneCall):
                    await self._handle_call_established(call)
                elif isinstance(call, types.PhoneCallDiscarded):
                    await self._handle_call_discarded(call)
            elif isinstance(update, types.UpdatePhoneCallSignalingData):
                session = self._session_by_call_id(update.phone_call_id)
                if session is not None and self.ntg is not None:
                    try:
                        await self.ntg.send_signaling_data(session.user_id, update.data)
                    except Exception as exc:  # noqa: BLE001
                        self._log.warning("Gagal memproses signaling masuk: %s", exc)

        self.app.add_handler(RawUpdateHandler(handle_raw_update))

    def _session_by_call_id(self, call_id: int) -> Optional[CallSession]:
        for session in self.sessions.values():
            if session.call_id == call_id:
                return session
        return None

    # ---------------------------------------------------------------- gemini
    def _live_factory(self, user_id: int, log):
        settings = self.settings
        tools_decl = self.tools.declarations()

        @asynccontextmanager
        async def factory() -> AsyncIterator[GeminiLiveSession]:
            assert self.gemini_client is not None
            config = genai_types.LiveConnectConfig(
                response_modalities=[genai_types.Modality.AUDIO],
                input_audio_transcription=genai_types.AudioTranscriptionConfig(),
                output_audio_transcription=genai_types.AudioTranscriptionConfig(),
                system_instruction=genai_types.Content(
                    parts=[genai_types.Part.from_text(text=settings.system_instruction)]
                ),
                realtime_input_config=genai_types.RealtimeInputConfig(
                    automatic_activity_detection=genai_types.AutomaticActivityDetection(
                        start_of_speech_sensitivity=genai_types.StartSensitivity.START_SENSITIVITY_HIGH,
                        end_of_speech_sensitivity=genai_types.EndSensitivity.END_SENSITIVITY_HIGH,
                        silence_duration_ms=800,
                    )
                ),
                tools=tools_decl,
            )
            async with self.gemini_client.aio.live.connect(
                model=settings.gemini_model, config=config
            ) as ws:
                log.info("Terhubung ke Gemini Live API (%s).", settings.gemini_model)
                yield GeminiLiveSession(ws, logger=log)

        return factory

    # ---------------------------------------------------------------- call flow
    async def _handle_call_requested(self, call: types.PhoneCallRequested) -> None:
        user_id = call.admin_id
        log = call_logger(user_id, call.id)
        log.info("Panggilan masuk dari user %s.", user_id)

        # Q12: record dibuat saat panggilan MASUK, sehingga penolakan pun tercatat.
        self._emit_call("call.incoming", {"tg_call_id": call.id, "user_id": user_id})
        self._observe_call("call_incoming", call.id, user_id)

        allowed = self.settings.allowed_user_id_set
        if allowed and user_id not in allowed:
            log.warning("Ditolak: user tidak ada di whitelist.")
            await self._reject_call(call, user_id, "rejected_whitelist")
            return

        if not self.rate_limiter.allow(user_id):
            log.warning(
                "Ditolak: rate-limit terlampaui (%d panggilan / %.0f dtk).",
                self.settings.max_calls_per_window,
                self.settings.call_window_seconds,
            )
            await self._reject_call(call, user_id, "rejected_ratelimit")
            return

        if user_id in self.sessions:
            # Panggilan ganda dari user yang sama (mis. update terduplikasi):
            # tolak yang baru agar sesi lama tidak tertimpa/bocor.
            log.warning("Ditolak: sudah ada sesi aktif untuk user ini.")
            await self._reject_call(call, user_id, "rejected_duplicate")
            return

        if len(self.sessions) >= self.settings.max_concurrent_calls:
            log.warning("Ditolak: kapasitas penuh (%d sesi).", len(self.sessions))
            await self._reject_call(call, user_id, "rejected_capacity")
            return

        assert self.ntg is not None
        session = CallSession(
            user_id=user_id,
            call_id=call.id,
            access_hash=call.access_hash,
            sink=NtgAudioSink(self.ntg, user_id),
            live_factory=self._live_factory(user_id, log),
            tools=self.tools,
            settings=self.settings,
            logger=log,
            on_stop=self._make_stop(user_id),
            on_event=self._make_session_event(call.id),
        )
        self.sessions[user_id] = session
        session.on_hangup = self._make_hangup(session)

        try:
            assert self.app is not None
            peer = types.InputPhoneCall(id=call.id, access_hash=call.access_hash)
            await self.app.invoke(functions.phone.ReceivedCall(peer=peer))  # pyright: ignore[reportArgumentType]

            dh = await self.app.invoke(functions.messages.GetDhConfig(version=0, random_length=256))
            dh_config = ntgcalls.DhConfig(g=dh.g, p=dh.p, random=dh.random)

            await self.ntg.create_p2p_call(user_id)
            g_b = await self.ntg.init_exchange(user_id, dh_config, call.g_a_hash)
            proto = to_tg_protocol(self.ntg.get_protocol(), getattr(call, "protocol", None))
            await self.app.invoke(functions.phone.AcceptCall(peer=peer, g_b=g_b, protocol=proto))  # pyright: ignore[reportArgumentType]
            log.info("AcceptCall terkirim; menunggu konfirmasi penelpon.")
        except Exception:  # noqa: BLE001
            log.exception("Gagal menerima panggilan.")
            self.sessions.pop(user_id, None)
            await session.close()
            self._emit_call(
                "call.ended",
                {"tg_call_id": call.id, "user_id": user_id, "outcome": OUTCOME_ERROR},
            )
            self._observe_call(
                "call_ended",
                call.id,
                user_id,
                outcome=OUTCOME_ERROR,
                end_reason=END_REASON_ERROR,
            )

    async def _reject_call(
        self, call: types.PhoneCallRequested, user_id: int, outcome: str
    ) -> None:
        """Tolak panggilan yang tidak lolos kebijakan; catat ke monitor & bus."""
        self._emit_call(
            "call.ended", {"tg_call_id": call.id, "user_id": user_id, "outcome": outcome}
        )
        self._observe_call(
            "call_ended",
            call.id,
            user_id,
            outcome=outcome,
            end_reason=END_REASON_REJECTED,
        )
        await self._discard_call(call, types.PhoneCallDiscardReasonBusy(), user_id)

    async def _handle_call_established(self, call: types.PhoneCall) -> None:
        user_id = call.admin_id or call.participant_id
        session = self.sessions.get(user_id) or self._session_by_call_id(call.id)
        if session is None:
            self._log.warning("Sesi untuk call id %s tidak ditemukan.", call.id)
            return

        if session.state != SessionState.INCOMING_CALL:
            # Update PhoneCall terduplikasi/terlambat: jangan setup media dua kali.
            self._log.warning(
                "PhoneCall untuk user %s diabaikan (state=%s).",
                session.user_id,
                session.state.value,
            )
            return

        log = call_logger(session.user_id, session.call_id)
        session.set_state(SessionState.CONNECTING)

        # Call sudah aktif di Telegram -> signaling ICE aman dikirim.
        session.signaling_ready = True
        assert self.signaling is not None
        self.signaling.flush_pending(session)

        try:
            assert self.ntg is not None
            await self.ntg.exchange_keys(session.user_id, call.g_a_or_b, call.key_fingerprint)
            rtc_servers = [to_ntg_rtc_server(conn) for conn in call.connections]
            lib_versions = list(call.protocol.library_versions) if call.protocol else ["13.0.0"]  # pyright: ignore[reportAttributeAccessIssue]

            await self.ntg.connect_p2p(
                session.user_id,
                rtc_servers,
                lib_versions,
                p2p_allowed=True,
                custom_parameters=None,
            )

            media = external_audio_media(self.settings.tg_sample_rate, keep_open=True)
            await self.ntg.set_stream_sources(session.user_id, ntgcalls.StreamMode.CAPTURE, media)
            await self.ntg.set_stream_sources(session.user_id, ntgcalls.StreamMode.PLAYBACK, media)

            log.info("Media P2P terhubung; membuka sesi Gemini.")
            session.start()
            self._emit_call(
                "call.started",
                {"tg_call_id": session.call_id, "user_id": session.user_id},
            )
            self._observe_call("call_started", session.call_id, session.user_id)
        except Exception:  # noqa: BLE001
            log.exception("Gagal menyiapkan media/koneksi.")
            self.sessions.pop(session.user_id, None)
            await session.close()
            self._observe_call(
                "call_ended",
                session.call_id,
                session.user_id,
                outcome="error",
                end_reason="error",
            )

    async def _handle_call_discarded(self, call: types.PhoneCallDiscarded) -> None:
        session = self._session_by_call_id(call.id)
        if session is None:
            return
        # `hangup()` juga mem-pop sesi yang sama setelah `await`; tanpa penjaga ini
        # `call.ended` terbit dua kali bila keduanya berjalan bersamaan.
        if self.sessions.pop(session.user_id, None) is None:
            self._log.debug("Sesi sudah dilepas; call.ended dilewati.")
            return
        duration = session.duration_seconds
        end_reason = session.end_reason or END_REASON_CALLER
        call_logger(session.user_id, session.call_id).info("Panggilan berakhir.")
        self._emit_call(
            "call.ended",
            {
                "tg_call_id": session.call_id,
                "user_id": session.user_id,
                "outcome": OUTCOME_ANSWERED,
                "duration_sec": duration,
                "end_reason": end_reason,
            },
        )
        await session.close()
        self._observe_call(
            "call_ended",
            session.call_id,
            session.user_id,
            outcome=OUTCOME_ANSWERED,
            end_reason=end_reason,
            duration_sec=duration,
        )

    async def _discard_call(self, call, reason, user_id: int) -> None:
        if self.app is None:
            return
        peer = types.InputPhoneCall(id=call.id, access_hash=call.access_hash)
        try:
            await self.app.invoke(
                functions.phone.DiscardCall(
                    peer=peer, duration=0, reason=reason, connection_id=0  # pyright: ignore[reportArgumentType]
                )
            )
        except Exception:  # noqa: BLE001
            self._log.exception("Gagal menolak panggilan user=%s", user_id)

    def _make_stop(self, user_id: int):
        async def stop() -> None:
            if self.ntg is not None:
                try:
                    await self.ntg.stop(user_id)
                except Exception:  # noqa: BLE001
                    pass

        return stop

    def _make_session_event(self, call_id: int) -> Optional[Callable[[str, dict], None]]:
        """Hook peristiwa sesi (transkrip/tool) untuk satu panggilan.

        Mengembalikan `None` bila tidak ada pemantau, sehingga `CallSession`
        tidak melakukan apa pun (jalur audio tetap nol tambahan).
        """
        observer = self._call_observer
        if observer is None:
            return None

        def on_event(event: str, data: dict) -> None:
            try:
                observer.session_event(call_id, event, data)
            except Exception:  # noqa: BLE001 - kegagalan monitor tak boleh mengganggu sesi
                self._log.debug("Gagal mengirim event sesi '%s'.", event, exc_info=True)

        return on_event

    def _make_hangup(self, session: "CallSession"):
        """Callback untuk mengakhiri panggilan dari sisi AI (tool end_call)."""

        async def hangup() -> None:
            log = call_logger(session.user_id, session.call_id)
            if self.app is not None:
                peer = types.InputPhoneCall(
                    id=session.call_id, access_hash=session.access_hash
                )
                try:
                    await self.app.invoke(
                        functions.phone.DiscardCall(
                            peer=peer,  # pyright: ignore[reportArgumentType]
                            duration=session.duration_seconds,
                            reason=types.PhoneCallDiscardReasonHangup(),  # pyright: ignore[reportArgumentType]
                            connection_id=0,
                        )
                    )
                    log.info("Panggilan diakhiri oleh AI (DiscardCall terkirim).")
                except Exception:  # noqa: BLE001
                    log.exception("Gagal mengirim DiscardCall.")
            if self.sessions.pop(session.user_id, None) is None:
                self._log.debug("Sesi sudah dilepas; call.ended dilewati.")
                return
            end_reason = session.end_reason or END_REASON_AI
            await session.close()
            self._emit_call(
                "call.ended",
                {
                    "tg_call_id": session.call_id,
                    "user_id": session.user_id,
                    "outcome": OUTCOME_ANSWERED,
                    "duration_sec": session.duration_seconds,
                    "end_reason": end_reason,
                },
            )
            self._observe_call(
                "call_ended",
                session.call_id,
                session.user_id,
                outcome=OUTCOME_ANSWERED,
                end_reason=end_reason,
                duration_sec=session.duration_seconds,
            )

        return hangup
