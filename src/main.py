#!/usr/bin/env python3
"""
Telegent: Telegram Voice Call + Google Gemini Live API
Proof of Concept - AI Voice Agent Real-Time Telepon P2P

Lifecycle Sesi:
IDLE -> INCOMING_CALL -> CONNECTING -> ACTIVE -> ENDING -> IDLE
"""

import argparse
import asyncio
from enum import Enum
import os
import sys
import time
from typing import Dict, Optional, Set

import numpy as np
import ntgcalls
from pyrogram import Client
from pyrogram.handlers import RawUpdateHandler
from pyrogram.raw import functions, types
from google import genai
from google.genai import types as genai_types

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.audio_resampler import pcm48k_to_pcm16k, pcm24k_to_pcm48k


class SessionState(Enum):
    IDLE = "IDLE"
    INCOMING_CALL = "INCOMING_CALL"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    ENDING = "ENDING"


# Parameter Audio Telegram VoIP
TG_SAMPLE_RATE = 48000
TG_FRAME_MS = 10
TG_FRAME_BYTES = int(TG_SAMPLE_RATE * (TG_FRAME_MS / 1000.0) * 2)  # 960 bytes (10 ms per packet)

# Persona Asisten Suara
DEFAULT_SYSTEM_INSTRUCTION = (
    "Anda adalah asisten suara AI yang ramah, ringkas, dan berbicara dalam bahasa Indonesia yang santun "
    "dan natural seperti sedang berbicara di telepon. Jawab secara padat (1-2 kalimat) karena ini adalah percakapan telepon langsung."
)
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-live-preview"


def to_ntg_rtc_server(conn) -> ntgcalls.RTCServer:
    if isinstance(conn, types.PhoneConnectionWebrtc):
        return ntgcalls.RTCServer(
            id=conn.id,
            ipv4=conn.ip,
            ipv6=conn.ipv6,
            port=conn.port,
            username=conn.username,
            password=conn.password,
            turn=conn.turn,
            stun=conn.stun,
            tcp=False,
            peer_tag=None,
        )
    else:
        return ntgcalls.RTCServer(
            id=conn.id,
            ipv4=conn.ip,
            ipv6=conn.ipv6,
            port=conn.port,
            username=None,
            password=None,
            turn=False,
            stun=False,
            tcp=conn.tcp,
            peer_tag=conn.peer_tag,
        )


def to_tg_protocol(proto: ntgcalls.Protocol, caller_proto: Optional[types.PhoneCallProtocol] = None) -> types.PhoneCallProtocol:
    if caller_proto:
        return types.PhoneCallProtocol(
            min_layer=min(proto.min_layer, caller_proto.min_layer),
            max_layer=min(proto.max_layer, caller_proto.max_layer),
            udp_p2p=proto.udp_p2p and caller_proto.udp_p2p,
            udp_reflector=proto.udp_reflector or caller_proto.udp_reflector,
            library_versions=list(caller_proto.library_versions),
        )
    return types.PhoneCallProtocol(
        min_layer=proto.min_layer,
        max_layer=proto.max_layer,
        udp_p2p=proto.udp_p2p,
        udp_reflector=proto.udp_reflector,
        library_versions=list(proto.library_versions),
    )


class CallSession:
    """Mengelola lifecycle dan worker pipeline satu panggilan telepon aktif."""

    def __init__(self, user_id: int, call_id: int, access_hash: int, agent: "TelegentAgent"):
        self.user_id = user_id
        self.call_id = call_id
        self.access_hash = access_hash
        self.agent = agent
        self.state = SessionState.INCOMING_CALL

        # Queue & buffer untuk audio dua arah
        self.inbound_audio_buffer = bytearray()
        self.outbound_pcm_buffer = bytearray()
        self.gemini_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=150)
        # Kapasitas besar agar audio AI tidak pernah dibuang saat Gemini mengirim
        # lebih cepat dari realtime (buffer ~15 detik pada 10 ms/frame).
        self.tg_out_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1500)

        self.tasks: list[asyncio.Task] = []
        self.gemini_session = None
        self.inbound_frame_count = 0
        self.is_greeting = True
        self.gemini_turn_done = False

        # Signaling WebRTC (ICE) hanya boleh dikirim setelah Telegram menandai
        # call aktif (update `types.PhoneCall` diterima). Sebelum itu, data
        # ditahan agar tidak memicu error 400 CALL_NOT_ACTIVE.
        self.signaling_ready = False
        self.pending_signaling: list[bytes] = []

    def set_state(self, new_state: SessionState):
        print(f"[Session {self.user_id}] Transisi status: {self.state.value} -> {new_state.value}", flush=True)
        self.state = new_state

    def flush_outbound(self):
        """Membersihkan antrean audio keluar ke Telegram saat interupsi terdeteksi."""
        dropped = 0
        self.outbound_pcm_buffer.clear()
        while not self.tg_out_queue.empty():
            try:
                self.tg_out_queue.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped > 0:
            print(f"\n[Barge-In] Memotong audio respons! Mengosongkan {dropped} frame buffer.", flush=True)

    def finish_greeting(self):
        """Mengakhiri mode sapaan pembuka dan membersihkan akumulasi buffer audio."""
        if self.is_greeting:
            self.is_greeting = False
            while not self.gemini_in_queue.empty():
                try:
                    self.gemini_in_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self.inbound_audio_buffer.clear()
            print("\n[AI Siap Mendengarkan] Sapaan selesai. Silakan ajukan pertanyaan Anda!", flush=True)

    async def start_workers(self, gemini_session):
        self.gemini_session = gemini_session
        self.set_state(SessionState.ACTIVE)

        t1 = asyncio.create_task(self._gemini_sender_worker())
        t2 = asyncio.create_task(self._gemini_receiver_worker())
        t3 = asyncio.create_task(self._telegram_audio_sender_worker())
        self.tasks.extend([t1, t2, t3])

    async def _gemini_sender_worker(self):
        """Worker: Mengirim audio ke Gemini Live secara kontinu untuk memicu VAD."""
        silence_16k = b"\x00" * 640  # 20 ms silence pada 16 kHz
        interval = 0.020  # 20 ms
        next_send = time.monotonic()
        sent_speech_chunks = 0
        try:
            while self.state == SessionState.ACTIVE:
                # 1. Selama sapaan awal belum selesai, tahan streaming input dan jaga antrean tetap kosong
                if self.is_greeting:
                    while not self.gemini_in_queue.empty():
                        try:
                            self.gemini_in_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    await asyncio.sleep(0.02)
                    next_send = time.monotonic()
                    continue

                chunk_16k = None
                try:
                    chunk_16k = self.gemini_in_queue.get_nowait()
                    sent_speech_chunks += 1
                    if sent_speech_chunks % 50 == 0:
                        print(f"[Gemini In] Mengirim suara penelpon ke Gemini ({sent_speech_chunks} chunks)...", flush=True)
                except asyncio.QueueEmpty:
                    # Penelpon diam / jeda bicara -> kirim comfort silence agar VAD Gemini mendeteksi akhir kalimat
                    chunk_16k = silence_16k

                if self.gemini_session:
                    await self.gemini_session.send_realtime_input(
                        audio=genai_types.Blob(data=chunk_16k, mime_type="audio/pcm;rate=16000")
                    )

                now = time.monotonic()
                if now < next_send:
                    await asyncio.sleep(next_send - now)
                elif now - next_send > 0.1:
                    next_send = now

                next_send += interval
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Error _gemini_sender_worker] {e}", file=sys.stderr)

    async def _gemini_receiver_worker(self):
        """Worker: Menerima streaming audio dari Gemini, resample ke 48 kHz, masukkan ke Telegram out queue.

        PENTING: Pada SDK google-genai (lihat `google/genai/live.py`), method
        `session.receive()` HANYA mengembalikan SATU giliran model (turn) lalu
        generator berhenti begitu server mengirim `turn_complete=True`
        (`_is_interaction_complete`). Jika `receive()` di-iterasi hanya sekali,
        AI akan menjawab sapaan pembuka lalu DIAM selamanya karena tidak ada lagi
        yang membaca respons giliran berikutnya. Karena itu `receive()` wajib
        dipanggil ulang di dalam loop luar selama panggilan masih ACTIVE.
        """
        if self.gemini_session is None:
            return
        try:
            while self.state == SessionState.ACTIVE:
                # Setiap iterasi membuat generator `receive()` baru untuk satu giliran.
                async for response in self.gemini_session.receive():
                    if self.state != SessionState.ACTIVE:
                        break

                    server_content = response.server_content
                    if server_content is not None:
                        # 1. Transkripsi suara pengguna secara real-time
                        if server_content.input_transcription and server_content.input_transcription.text:
                            print(f"\n[Penelpon]: {server_content.input_transcription.text}", flush=True)

                        # 2. Transkripsi ucapan AI secara real-time
                        if server_content.output_transcription and server_content.output_transcription.text:
                            print(server_content.output_transcription.text, end="", flush=True)

                        # 3. Deteksi interupsi (pengguna berbicara memotong AI)
                        if server_content.interrupted:
                            if not self.is_greeting:
                                self.flush_outbound()
                                continue

                        # 4. Tangkap audio potongan dari model turn
                        model_turn = server_content.model_turn
                        if model_turn and model_turn.parts:
                            self.gemini_turn_done = False
                            for part in model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    pcm_24k = part.inline_data.data
                                    # Resampling 24 kHz -> 48 kHz (smooth linear interpolation)
                                    pcm_48k = pcm24k_to_pcm48k(pcm_24k)

                                    # Buffer dan bagi ke frame 10 ms (960 bytes) presisi
                                    self.outbound_pcm_buffer.extend(pcm_48k)
                                    while len(self.outbound_pcm_buffer) >= TG_FRAME_BYTES:
                                        chunk = bytes(self.outbound_pcm_buffer[:TG_FRAME_BYTES])
                                        del self.outbound_pcm_buffer[:TG_FRAME_BYTES]
                                        # Backpressure tanpa membuang frame agar audio tidak
                                        # terpotong saat Gemini memproduksi lebih cepat dari realtime.
                                        if self.tg_out_queue.full():
                                            try:
                                                await asyncio.wait_for(self.tg_out_queue.put(chunk), timeout=5.0)
                                            except asyncio.TimeoutError:
                                                # Konsumen macet (jarang): buang frame tertua sebagai jalan terakhir.
                                                try:
                                                    self.tg_out_queue.get_nowait()
                                                except asyncio.QueueEmpty:
                                                    pass
                                                try:
                                                    self.tg_out_queue.put_nowait(chunk)
                                                except Exception:
                                                    pass
                                        else:
                                            self.tg_out_queue.put_nowait(chunk)

                        if server_content.turn_complete:
                            self.gemini_turn_done = True
                            if self.is_greeting:
                                self.finish_greeting()
                            else:
                                print(" [AI selesai menjawab]\n", flush=True)

                # Generator `receive()` selesai untuk satu giliran. Bila panggilan
                # masih ACTIVE, loop luar akan memanggil `receive()` lagi untuk
                # giliran berikutnya.
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Error _gemini_receiver_worker] {e}", file=sys.stderr)

    async def _telegram_audio_sender_worker(self):
        """Worker: Mengirimkan frame audio 48 kHz (10 ms) ke media engine Telegram.

        Kunci audio yang mulus: frame HARUS dikirim pada cadence stabil 10 ms
        (`ntgcalls` AudioSink menaruh frame tiap 10 ms). Berhenti mengirim
        (misalnya menunggu pre-buffer) membuat jitter buffer WebRTC di sisi
        penelpon underrun sehingga suara tersendat/patah. Karena itu, bila belum
        ada audio AI yang siap, kita tetap mengirim frame SENYAP agar cadence
        terjaga — pre-buffer hanya menahan audio AI, tidak menghentikan kiriman.
        """
        interval = 0.010  # 10 ms per frame
        silence = b"\x00" * TG_FRAME_BYTES
        frame_data = ntgcalls.FrameData(0, ntgcalls.VideoRotation.VIDEO_ROTATION_0, 0, 0)
        prefill_frames = 15  # ~150 ms buffer awal agar onset audio AI mulus
        next_send = time.monotonic()
        is_playing = False
        try:
            while self.state == SessionState.ACTIVE:
                if self.agent.ntg is None:
                    await asyncio.sleep(interval)
                    next_send = time.monotonic()
                    continue

                # 1. Tentukan frame yang dikirim: audio AI bila siap, jika tidak -> senyap.
                frame = silence
                if is_playing:
                    try:
                        frame = self.tg_out_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        # Audio AI habis di tengah giliran -> kirim senyap, cadence tetap jalan.
                        is_playing = False
                if not is_playing:
                    if self.tg_out_queue.qsize() >= prefill_frames:
                        is_playing = True
                        try:
                            frame = self.tg_out_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            is_playing = False
                            frame = silence
                    else:
                        frame = silence

                # 2. Pace ke cadence 10 ms berbasis deadline absolut (anti-drift).
                now = time.monotonic()
                if now < next_send:
                    await asyncio.sleep(next_send - now)
                elif now - next_send > 0.05:
                    next_send = now

                try:
                    await self.agent.ntg.send_external_frame(
                        self.user_id,
                        ntgcalls.StreamDevice.MICROPHONE,
                        frame,
                        frame_data,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[Error send_external_frame] {e}", file=sys.stderr)

                next_send += interval
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Error _telegram_audio_sender_worker] {e}", file=sys.stderr)

    def handle_incoming_telegram_pcm(self, pcm_bytes: bytes):
        """Dijalankan di thread asyncio loop saat paket PCM diterima dari penelpon."""
        if self.state != SessionState.ACTIVE:
            return

        self.inbound_frame_count += 1
        if self.inbound_frame_count == 1:
            print(f"\n[Media In] Audio pertama dari penelpon terhubung! ({len(pcm_bytes)} bytes)", flush=True)
        elif self.inbound_frame_count % 50 == 0:
            print(f"[Media In] {self.inbound_frame_count} paket audio diterima dari penelpon...", flush=True)

        self.inbound_audio_buffer.extend(pcm_bytes)

        # 20 ms pada 48 kHz = 1920 bytes -> downsample ke 16 kHz = 640 bytes (20 ms)
        while len(self.inbound_audio_buffer) >= 1920:
            chunk_48k = bytes(self.inbound_audio_buffer[:1920])
            del self.inbound_audio_buffer[:1920]

            chunk_16k = pcm48k_to_pcm16k(chunk_48k)
            samples = np.frombuffer(chunk_16k, dtype=np.int16)
            max_amp = int(np.max(np.abs(samples))) if len(samples) > 0 else 0

            # Logging tingkat sinyal suara penelpon setiap 100 frame (~2 detik)
            if self.inbound_frame_count % 100 == 0 and len(self.inbound_audio_buffer) < 1920:
                print(f"[Penelpon Audio] Level sinyal suara: peak={max_amp} (aktif)", flush=True)

            # Kirim audio murni hasil downsample tanpa clipping/muting buatan.
            # VAD neural bawaan Gemini Live API secara otomatis mendeteksi ucapan vs keheningan.
            try:
                self.gemini_in_queue.put_nowait(chunk_16k)
            except asyncio.QueueFull:
                try:
                    self.gemini_in_queue.get_nowait()
                    self.gemini_in_queue.put_nowait(chunk_16k)
                except Exception:
                    pass

    async def close(self):
        """Membersihkan dan menutup sesi panggilan."""
        self.set_state(SessionState.ENDING)
        for t in self.tasks:
            t.cancel()

        self.inbound_audio_buffer.clear()
        self.pending_signaling.clear()
        self.flush_outbound()

        if self.agent.ntg:
            try:
                await self.agent.ntg.stop(self.user_id)
            except Exception:
                pass

        self.set_state(SessionState.IDLE)


class TelegentAgent:
    def __init__(
        self,
        telegram_api_id: int,
        telegram_api_hash: str,
        gemini_api_key: str,
        session_name: str = "userbot_session",
        gemini_model: str = DEFAULT_GEMINI_MODEL,
        allowed_user_ids: Optional[Set[int]] = None,
    ):
        self.api_id = telegram_api_id
        self.api_hash = telegram_api_hash
        self.gemini_api_key = gemini_api_key
        self.session_name = session_name
        self.gemini_model = gemini_model
        self.allowed_user_ids = allowed_user_ids or set()

        self.app: Optional[Client] = None
        self.ntg: Optional[ntgcalls.NTgCalls] = None
        self.gemini_client: Optional[genai.Client] = None
        self.active_sessions: Dict[int, CallSession] = {}
        self.loop = None

    async def _send_signaling_data(self, session: "CallSession", data: bytes):
        """Mengirim data signaling ICE ke Telegram dengan retry singkat.

        Telegram kadang belum menandai call aktif tepat setelah update
        `types.PhoneCall` diterima (race kondisi), sehingga
        `phone.SendSignalingData` sesaat mengembalikan 400 CALL_NOT_ACTIVE.
        Retry singkat mencegah kandidat ICE terbuang.
        """
        if not self.app:
            return
        peer = types.InputPhoneCall(id=session.call_id, access_hash=session.access_hash)
        for attempt in range(5):
            try:
                await self.app.invoke(functions.phone.SendSignalingData(peer=peer, data=data))
                return
            except Exception as e:
                if "CALL_NOT_ACTIVE" in str(e) and attempt < 4:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                print(f"[Signaling error] {e}", file=sys.stderr)
                return

    def _dispatch_signaling(self, session: "CallSession", data: bytes):
        """Menjadwalkan pengiriman signaling ke event loop asyncio utama."""
        if not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self._send_signaling_data(session, data), self.loop)

    def _flush_pending_signaling(self, session: "CallSession"):
        """Mengirim semua data signaling yang sempat ditahan sebelum call aktif."""
        if not session.pending_signaling:
            return
        pending = session.pending_signaling
        session.pending_signaling = []
        print(f"[Signaling] Mengirim {len(pending)} paket ICE yang tertahan.", flush=True)
        for data in pending:
            self._dispatch_signaling(session, data)

    def _setup_ntg_callbacks(self):
        def on_signaling_data(user_id: int, data: bytes):
            session = self.active_sessions.get(user_id)
            if not session or not self.app or not self.loop:
                return

            # Bila Telegram belum menandai call aktif, tahan data signaling dulu
            # agar tidak memicu error 400 CALL_NOT_ACTIVE. Data dikirim saat call
            # terkonfirmasi (lihat `_flush_pending_signaling`).
            if not session.signaling_ready:
                if len(session.pending_signaling) < 512:
                    session.pending_signaling.append(data)
                return

            self._dispatch_signaling(session, data)

        def on_connection_change(user_id: int, info: ntgcalls.ConnectionInfo):
            state_name = str(info.state).split(".")[-1]
            kind_name = str(info.kind).split(".")[-1]
            print(f"[Media Connection] User {user_id}: {state_name} ({kind_name})", flush=True)

        def on_frames(user_id: int, mode, _device, frames):
            if mode != ntgcalls.StreamMode.PLAYBACK:
                return
            session = self.active_sessions.get(user_id)
            if not session or not self.loop:
                return

            raw_bytes = bytearray()
            for f in frames:
                if f.data:
                    raw_bytes.extend(f.data)

            if raw_bytes:
                # Thread-safe dispatch ke loop asyncio utama!
                self.loop.call_soon_threadsafe(session.handle_incoming_telegram_pcm, bytes(raw_bytes))

        if self.ntg:
            self.ntg.on_signaling_data(on_signaling_data)
            self.ntg.on_connection_change(on_connection_change)
            self.ntg.on_frames(on_frames)

    def _setup_pyrogram_handlers(self):
        async def handle_raw_update(_client: Client, update, _users, _chats):
            if isinstance(update, types.UpdatePhoneCall):
                call = update.phone_call
                print(f"\n[PhoneCall Update] Status: {type(call).__name__} (Call ID: {getattr(call, 'id', 'N/A')})", flush=True)
                if isinstance(call, types.PhoneCallRequested):
                    await self._handle_call_requested(call)
                elif isinstance(call, types.PhoneCall):
                    await self._handle_call_established(call)
                elif isinstance(call, types.PhoneCallDiscarded):
                    await self._handle_call_discarded(call)

            elif isinstance(update, types.UpdatePhoneCallSignalingData):
                call_id = update.phone_call_id
                target_user = None
                for uid, sess in self.active_sessions.items():
                    if sess.call_id == call_id:
                        target_user = uid
                        break
                if target_user and self.ntg:
                    try:
                        await self.ntg.send_signaling_data(target_user, update.data)
                    except Exception as e:
                        print(f"[Signaling in error] {e}", file=sys.stderr)

        if self.app:
            self.app.add_handler(RawUpdateHandler(handle_raw_update))

    async def _handle_call_requested(self, call: types.PhoneCallRequested):
        user_id = call.admin_id
        print(f"\n[Incoming Call] Panggilan masuk dari Telegram User ID: {user_id}", flush=True)

        if self.allowed_user_ids and user_id not in self.allowed_user_ids:
            print(f"[Ditolak] User {user_id} tidak berada dalam whitelist.", flush=True)
            peer = types.InputPhoneCall(id=call.id, access_hash=call.access_hash)
            if self.app:
                await self.app.invoke(
                    functions.phone.DiscardCall(
                        peer=peer,
                        duration=0,
                        reason=types.PhoneCallDiscardReasonBusy(),
                        connection_id=0,
                    )
                )
            return

        session = CallSession(user_id, call.id, call.access_hash, self)
        self.active_sessions[user_id] = session

        try:
            peer = types.InputPhoneCall(id=call.id, access_hash=call.access_hash)
            if self.app:
                await self.app.invoke(functions.phone.ReceivedCall(peer=peer))

            if self.app:
                dh = await self.app.invoke(functions.messages.GetDhConfig(version=0, random_length=256))
                dh_config = ntgcalls.DhConfig(g=dh.g, p=dh.p, random=dh.random)
            else:
                return

            # Inisialisasi call di NTgCalls. Stream media (CAPTURE & PLAYBACK)
            # baru dipasang setelah koneksi P2P dibuka di `_handle_call_established`,
            # persis seperti PoC Fase 2 yang telah tervalidasi. Memasang source
            # terlalu dini memicu pengiriman signaling sebelum call dianggap aktif
            # oleh Telegram (error 400 CALL_NOT_ACTIVE).
            if self.ntg:
                await self.ntg.create_p2p_call(user_id)
                g_b = await self.ntg.init_exchange(user_id, dh_config, call.g_a_hash)
                proto = to_tg_protocol(self.ntg.get_protocol(), getattr(call, "protocol", None))

                if self.app:
                    await self.app.invoke(functions.phone.AcceptCall(peer=peer, g_b=g_b, protocol=proto))
                print("[Signaling] Panggilan diterima (AcceptCall terkirim). Menunggu konfirmasi caller...", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Error _handle_call_requested] {e}", file=sys.stderr)

    async def _handle_call_established(self, call: types.PhoneCall):
        try:
            user_id = call.admin_id or call.participant_id
            session = self.active_sessions.get(user_id)
            if not session:
                for s in self.active_sessions.values():
                    if s.call_id == call.id:
                        session = s
                        user_id = s.user_id
                        break
            if not session:
                print(f"[Warning] Session untuk Call ID {call.id} (User {user_id}) tidak ditemukan.", flush=True)
                return

            session.set_state(SessionState.CONNECTING)

            # Telegram sudah mengonfirmasi call aktif (update `types.PhoneCall`
            # diterima), sehingga signaling ICE kini aman dikirim. Lepaskan paket
            # signaling yang sempat ditahan agar tidak memicu CALL_NOT_ACTIVE.
            session.signaling_ready = True
            self._flush_pending_signaling(session)

            if self.ntg:
                await self.ntg.exchange_keys(user_id, call.g_a_or_b, call.key_fingerprint)
                rtc_servers = [to_ntg_rtc_server(conn) for conn in call.connections]
                lib_versions = list(call.protocol.library_versions) if call.protocol else ["13.0.0"]

                await self.ntg.connect_p2p(
                    user_id,
                    rtc_servers,
                    lib_versions,
                    p2p_allowed=True,
                    custom_parameters=None,
                )

                # Pasang CAPTURE & PLAYBACK SETELAH koneksi media dibuka.
                # Quirk ntgcalls 3.x: sink PLAYBACK harus diarahkan ke parameter
                # `microphone` (konteks eksternal) agar frame audio masuk
                # diteruskan ke callback `on_frames`, bukan ke speaker fisik OS.
                audio_desc = ntgcalls.AudioDescription(
                    media_source=ntgcalls.MediaSource.EXTERNAL,
                    sample_rate=48000,
                    channel_count=1,
                    input="",
                    keep_open=True,
                )
                media = ntgcalls.MediaDescription(audio_desc, None, None, None)
                await self.ntg.set_stream_sources(user_id, ntgcalls.StreamMode.CAPTURE, media)
                await self.ntg.set_stream_sources(user_id, ntgcalls.StreamMode.PLAYBACK, media)

            # Buka sesi Gemini Live API
            print(f"[Gemini] Membuka sesi streaming Gemini Live API ({self.gemini_model})...", flush=True)
            config = genai_types.LiveConnectConfig(
                response_modalities=[genai_types.Modality.AUDIO],
                input_audio_transcription=genai_types.AudioTranscriptionConfig(),
                output_audio_transcription=genai_types.AudioTranscriptionConfig(),
                system_instruction=genai_types.Content(
                    parts=[genai_types.Part.from_text(text=DEFAULT_SYSTEM_INSTRUCTION)]
                ),
                realtime_input_config=genai_types.RealtimeInputConfig(
                    automatic_activity_detection=genai_types.AutomaticActivityDetection(
                        start_of_speech_sensitivity=genai_types.StartSensitivity.START_SENSITIVITY_HIGH,
                        end_of_speech_sensitivity=genai_types.EndSensitivity.END_SENSITIVITY_HIGH,
                        silence_duration_ms=800,
                    )
                ),
            )

            async def run_gemini():
                try:
                    if self.gemini_client:
                        async with self.gemini_client.aio.live.connect(model=self.gemini_model, config=config) as g_sess:
                            print("[Gemini] Terhubung ke Gemini Live API! Audio dua arah aktif.", flush=True)
                            await session.start_workers(g_sess)

                            # Sapaan awal otomatis
                            try:
                                await g_sess.send_client_content(
                                    turns=[
                                        genai_types.Content(
                                            role="user",
                                            parts=[genai_types.Part.from_text(text="Sapa penelpon dengan ramah dan singkat: 'Halo, dengan siapa saya berbicara? Ada yang bisa dibantu?'")],
                                        )
                                    ],
                                    turn_complete=True,
                                )
                            except Exception as e:
                                print(f"[Warning initial greeting] {e}", file=sys.stderr)

                            # Timer pengaman agar sapaan tidak mengunci mikrofon
                            async def auto_clear_greeting():
                                await asyncio.sleep(4.0)
                                session.finish_greeting()
                            asyncio.create_task(auto_clear_greeting())

                            # Loop penjaga sampai sesi berakhir
                            while session.state == SessionState.ACTIVE:
                                await asyncio.sleep(0.5)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[Gemini Session Error] {e}", file=sys.stderr)
                finally:
                    await session.close()

            asyncio.create_task(run_gemini())
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Error _handle_call_established] {e}", file=sys.stderr)

    async def _handle_call_discarded(self, call: types.PhoneCallDiscarded):
        target_user = None
        for uid, sess in list(self.active_sessions.items()):
            if sess.call_id == call.id:
                target_user = uid
                break

        if target_user is not None:
            print(f"[Call Discarded] Panggilan dengan User {target_user} selesai.", flush=True)
            session = self.active_sessions.pop(target_user, None)
            if session:
                await session.close()

    async def start(self):
        self.loop = asyncio.get_running_loop()
        self.app = Client(self.session_name, api_id=self.api_id, api_hash=self.api_hash)
        self.ntg = ntgcalls.NTgCalls()
        self.gemini_client = genai.Client(api_key=self.gemini_api_key)

        self._setup_ntg_callbacks()
        self._setup_pyrogram_handlers()

        print(f"Menginisialisasi Telegent Client '{self.session_name}'...", flush=True)
        assert self.app is not None
        await self.app.start()
        me = await self.app.get_me()
        print(f"Login sukses sebagai: {me.first_name} (@{me.username or 'Tanpa Username'}, ID: {me.id})", flush=True)
        print(f"Dispatcher Handlers: {len(self.app.dispatcher.groups.get(0, []))} handler terpasang.", flush=True)
        print("Telegent AI Voice Agent aktif & siap menerima panggilan! (Tekan Ctrl+C untuk berhenti)", flush=True)
        await asyncio.Event().wait()


def main():
    parser = argparse.ArgumentParser(description="Telegent - Telegram Voice Call AI Voice Agent")
    parser.add_argument("--api-id", type=int, default=os.environ.get("TELEGRAM_API_ID"))
    parser.add_argument("--api-hash", type=str, default=os.environ.get("TELEGRAM_API_HASH"))
    parser.add_argument("--gemini-api-key", type=str, default=os.environ.get("GEMINI_API_KEY"))
    parser.add_argument("--session", type=str, default="userbot_session")
    parser.add_argument("--gemini-model", type=str, default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--allow-user", type=int, action="append", help="ID pengguna yang diizinkan menelepon")
    args = parser.parse_args()

    if not args.api_id or not args.api_hash:
        print("Error: Argumen --api-id dan --api-hash (atau env var TELEGRAM_API_ID & TELEGRAM_API_HASH) diperlukan.", file=sys.stderr)
        sys.exit(1)

    if not args.gemini_api_key:
        print("Error: Argumen --gemini-api-key (atau env var GEMINI_API_KEY) diperlukan.", file=sys.stderr)
        sys.exit(1)

    allowed_set = set(args.allow_user) if args.allow_user else set()

    agent = TelegentAgent(
        telegram_api_id=args.api_id,
        telegram_api_hash=args.api_hash,
        gemini_api_key=args.gemini_api_key,
        session_name=args.session,
        gemini_model=args.gemini_model,
        allowed_user_ids=allowed_set,
    )

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("\nTelegent Agent dimatikan.")


if __name__ == "__main__":
    main()
