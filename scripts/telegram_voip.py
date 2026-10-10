#!/usr/bin/env python3
"""
PoC Telegram VoIP - Panggilan Masuk Privat 1-on-1 (Fase 2)

Menggunakan:
- Pyrogram (Signaling MTProto: phone.acceptCall, phone.receivedCall, dll.)
- NTgCalls (WebRTC P2P Media Transport & Enkripsi Diffie-Hellman)

Fitur:
- Menerima panggilan masuk 1-on-1 otomatis
- Mode Loopback (memantulkan suara penelpon kembali)
- Mode Test Tone (mengirimkan nada 440 Hz ke panggilan)
- Pembersihan resource dan pemutusan panggilan bersih
"""

import argparse
import asyncio
import math
import os
import struct
import sys
from typing import Dict, Optional, Set

from dotenv import load_dotenv
import ntgcalls
from pyrogram import Client
from pyrogram.handlers import RawUpdateHandler
from pyrogram.raw import functions, types

load_dotenv()


def to_ntg_rtc_server(conn) -> ntgcalls.RTCServer:
    """Konversi koneksi server Telegram ke objek RTCServer NTgCalls."""
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
    else:  # types.PhoneConnection
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
    """Konversi konfigurasi protokol NTgCalls ke tipe MTProto PhoneCallProtocol."""
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


class TelegramVoIPAgent:
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str = "userbot_session",
        mode: str = "loopback",
        allowed_user_ids: Optional[Set[int]] = None,
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.mode = mode
        self.allowed_user_ids = allowed_user_ids or set()

        self.app: Optional[Client] = None
        self.ntg: Optional[ntgcalls.NTgCalls] = None

        # Pelacakan sesi panggilan aktif: user_id -> call_info
        self.active_calls: Dict[int, dict] = {}
        self.outbound_queues: Dict[int, asyncio.Queue] = {}
        self.sender_tasks: Dict[int, asyncio.Task] = {}
        self.loop = None

    def _setup_ntg_callbacks(self):
        """Mendaftarkan callback internal NTgCalls."""

        def on_signaling_data(user_id: int, data: bytes):
            call_info = self.active_calls.get(user_id)
            if not call_info or not self.app:
                return

            peer = types.InputPhoneCall(
                id=call_info["call_id"],
                access_hash=call_info["access_hash"],
            )

            async def send_sig():
                try:
                    await self.app.invoke(
                        functions.phone.SendSignalingData(peer=peer, data=data)
                    )
                except Exception as e:
                    print(f"[Error send_signaling_data] User {user_id}: {e}", file=sys.stderr)

            asyncio.run_coroutine_threadsafe(send_sig(), self.loop)

        def on_connection_change(user_id: int, info: ntgcalls.ConnectionInfo):
            state_name = str(info.state).split(".")[-1]
            kind_name = str(info.kind).split(".")[-1]
            print(f"[VoIP Status] User {user_id}: State={state_name}, Kind={kind_name}", flush=True)

        def on_frames(user_id: int, mode, _device, frames):
            # Hanya proses audio masuk dari caller (PLAYBACK mode)
            if mode != ntgcalls.StreamMode.PLAYBACK:
                return

            q = self.outbound_queues.get(user_id)
            if not q:
                return

            for frame in frames:
                if frame.data and len(frame.data) > 0:
                    if self.mode == "loopback":
                        try:
                            q.put_nowait(frame.data)
                        except asyncio.QueueFull:
                            # Drop frame lama jika buffer penuh
                            try:
                                q.get_nowait()
                                q.put_nowait(frame.data)
                            except Exception:
                                pass

        self.ntg.on_signaling_data(on_signaling_data)
        self.ntg.on_connection_change(on_connection_change)
        self.ntg.on_frames(on_frames)

    def _setup_pyrogram_handlers(self):
        """Mendaftarkan handler update mentah MTProto dari Pyrogram."""

        async def handle_raw_update(_client: Client, update, _users, _chats):
            # 1. Update status panggilan
            if isinstance(update, types.UpdatePhoneCall):
                call = update.phone_call
                print(f"[PhoneCall Update] Status: {type(call).__name__} (Call ID: {getattr(call, 'id', 'N/A')})", flush=True)
                # Panggilan masuk baru diminta
                if isinstance(call, types.PhoneCallRequested):
                    await self._handle_incoming_call_request(call)

                # Panggilan sudah dikonfirmasi caller & siap koneksi media
                elif isinstance(call, types.PhoneCall):
                    await self._handle_call_established(call)

                # Panggilan ditutup / ditolak
                elif isinstance(call, types.PhoneCallDiscarded):
                    await self._handle_call_discarded(call)

            # 2. Update data signaling ICE / WebRTC
            elif isinstance(update, types.UpdatePhoneCallSignalingData):
                call_id = update.phone_call_id
                # Cari user_id yang sesuai dengan call_id
                target_user = None
                for uid, info in self.active_calls.items():
                    if info["call_id"] == call_id:
                        target_user = uid
                        break

                if target_user and self.ntg:
                    try:
                        await self.ntg.send_signaling_data(target_user, update.data)
                    except Exception as e:
                        print(f"[Error ntg.send_signaling_data] User {target_user}: {e}", file=sys.stderr)

        self.app.add_handler(RawUpdateHandler(handle_raw_update))

    async def _handle_incoming_call_request(self, call: types.PhoneCallRequested):
        user_id = call.admin_id
        print(f"\n[Incoming Call] Panggilan masuk dari Telegram User ID: {user_id}")

        if self.allowed_user_ids and user_id not in self.allowed_user_ids:
            print(f"[Akses Ditolak] User {user_id} tidak ada dalam daftar whitelist. Menolak panggilan...")
            peer = types.InputPhoneCall(id=call.id, access_hash=call.access_hash)
            await self.app.invoke(
                functions.phone.DiscardCall(
                    peer=peer,
                    duration=0,
                    reason=types.PhoneCallDiscardReasonBusy(),
                    connection_id=0,
                )
            )
            return

        peer = types.InputPhoneCall(id=call.id, access_hash=call.access_hash)

        # 1. Kirim notifikasi 'ReceivedCall' (status berdering di sisi penelepon)
        await self.app.invoke(functions.phone.ReceivedCall(peer=peer))
        print(f"[Signaling] Mengirim ReceivedCall ke Telegram server untuk Call ID: {call.id}")

        # 2. Ambil parameter Diffie-Hellman dari Telegram
        dh = await self.app.invoke(functions.messages.GetDhConfig(version=0, random_length=256))
        dh_config = ntgcalls.DhConfig(g=dh.g, p=dh.p, random=dh.random)

        # 3. Inisialisasi call di NTgCalls & jalankan DH step 1
        await self.ntg.create_p2p_call(user_id)
        g_b = await self.ntg.init_exchange(user_id, dh_config, call.g_a_hash)

        # 4. Terima panggilan secara formal lewat MTProto
        proto = to_tg_protocol(self.ntg.get_protocol(), getattr(call, "protocol", None))
        await self.app.invoke(
            functions.phone.AcceptCall(
                peer=peer,
                g_b=g_b,
                protocol=proto,
            )
        )
        print(f"[Signaling] Mengirim AcceptCall dengan parameter Diffie-Hellman (g_b) berhasil.")

        # Simpan metadata panggilan
        self.active_calls[user_id] = {
            "call_id": call.id,
            "access_hash": call.access_hash,
            "user_id": user_id,
        }
        self.outbound_queues[user_id] = asyncio.Queue(maxsize=100)

    async def _handle_call_established(self, call: types.PhoneCall):
        user_id = call.admin_id or call.participant_id
        call_info = self.active_calls.get(user_id)
        if not call_info:
            return

        print(f"[Signaling] Panggilan terverifikasi (State: PhoneCall). Menyelesaikan pertukaran kunci...")

        # 1. Verifikasi kunci kriptografi dengan caller
        await self.ntg.exchange_keys(user_id, call.g_a_or_b, call.key_fingerprint)

        # 2. Konversi server RTC yang diberikan Telegram
        rtc_servers = [to_ntg_rtc_server(conn) for conn in call.connections]
        lib_versions = list(call.protocol.library_versions) if call.protocol else ["13.0.0"]

        # 3. Hubungkan WebRTC media transport
        print(f"[Media] Membuka koneksi media P2P ke {len(rtc_servers)} server RTC...")
        await self.ntg.connect_p2p(
            user_id,
            rtc_servers,
            lib_versions,
            p2p_allowed=True,
            custom_parameters=None,
        )

        # 4. Konfigurasi audio stream sources
        # Quirk ntgcalls: Playback sink diarahkan ke context microphone eksternal
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
        print(f"[Media] Stream CAPTURE dan PLAYBACK aktif (48 kHz mono PCM). Mode: {self.mode.upper()}")

        # 5. Jalankan sender loop
        task = asyncio.create_task(self._outbound_sender_loop(user_id))
        self.sender_tasks[user_id] = task

    async def _handle_call_discarded(self, call: types.PhoneCallDiscarded):
        target_user = None
        for uid, info in list(self.active_calls.items()):
            if info["call_id"] == call.id:
                target_user = uid
                break

        if target_user is not None:
            reason = type(call.reason).__name__ if call.reason else "Normal"
            print(f"\n[Call Ended] Panggilan dengan User {target_user} berakhir. Alasan: {reason}")
            await self._cleanup_call(target_user)

    async def _cleanup_call(self, user_id: int):
        """Membersihkan resource setelah panggilan berakhir."""
        task = self.sender_tasks.pop(user_id, None)
        if task:
            task.cancel()

        self.outbound_queues.pop(user_id, None)
        self.active_calls.pop(user_id, None)

        try:
            await self.ntg.stop(user_id)
        except Exception:
            pass
        print(f"[Cleanup] Resource untuk User {user_id} berhasil dibersihkan.")

    async def _outbound_sender_loop(self, user_id: int):
        """Worker untuk mengirim frame audio 48 kHz mono 16-bit ke Telegram."""
        q = self.outbound_queues.get(user_id)
        if not q:
            return

        # Frame 10 ms pada 48 kHz = 480 samples = 960 bytes
        chunk_size = 960
        frame_data = ntgcalls.FrameData()

        sine_phase = 0.0
        tone_freq = 440.0

        try:
            while user_id in self.active_calls:
                if self.mode == "loopback":
                    # Ambil frame dari antrean loopback
                    data = await q.get()
                    # Pastikan data dikirim dalam kelipatan 960 bytes
                    for i in range(0, len(data), chunk_size):
                        sub_chunk = data[i : i + chunk_size]
                        if len(sub_chunk) == chunk_size:
                            await self.ntg.send_external_frame(
                                user_id,
                                ntgcalls.StreamDevice.MICROPHONE,
                                sub_chunk,
                                frame_data,
                            )
                            await asyncio.sleep(0.009)  # Cadence pacing ~10ms
                elif self.mode == "test_tone":
                    # Generate nada 440 Hz sintetis per 10 ms
                    samples = []
                    for _ in range(480):
                        sample_val = int(14000 * math.sin(sine_phase))
                        sine_phase += 2 * math.pi * tone_freq / 48000.0
                        if sine_phase > 2 * math.pi:
                            sine_phase -= 2 * math.pi
                        samples.append(sample_val)
                    tone_bytes = struct.pack(f"<{len(samples)}h", *samples)
                    await self.ntg.send_external_frame(
                        user_id,
                        ntgcalls.StreamDevice.MICROPHONE,
                        tone_bytes,
                        frame_data,
                    )
                    await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Error _outbound_sender_loop] User {user_id}: {e}", file=sys.stderr)

    async def start(self):
        """Memulai client Pyrogram dan mendengarkan panggilan masuk."""
        self.loop = asyncio.get_running_loop()
        self.app = Client(self.session_name, api_id=self.api_id, api_hash=self.api_hash)
        self.ntg = ntgcalls.NTgCalls()

        self._setup_ntg_callbacks()
        self._setup_pyrogram_handlers()

        print(f"Menginisialisasi Pyrogram Session '{self.session_name}'...", flush=True)
        await self.app.start()
        me = await self.app.get_me()
        print(f"Login sukses sebagai: {me.first_name} (@{me.username or 'Tanpa Username'}, ID: {me.id})", flush=True)
        print(f"Dispatcher Handlers: {len(self.app.dispatcher.groups.get(0, []))} handler terpasang.", flush=True)
        print("Menunggu panggilan Telegram masuk... (Tekan Ctrl+C untuk keluar)", flush=True)
        await asyncio.Event().wait()


def main():
    parser = argparse.ArgumentParser(description="PoC Telegram VoIP Incoming Call Responder")
    parser.add_argument("--api-id", type=int, default=os.environ.get("TELEGRAM_API_ID"))
    parser.add_argument("--api-hash", type=str, default=os.environ.get("TELEGRAM_API_HASH"))
    parser.add_argument("--session", type=str, default="userbot_session", help="Nama session Pyrogram")
    parser.add_argument("--mode", choices=["loopback", "test_tone"], default="loopback", help="Mode audio outbound")
    parser.add_argument("--allow-user", type=int, action="append", help="ID pengguna yang diizinkan menelepon")
    args = parser.parse_args()

    if not args.api_id or not args.api_hash:
        print(
            "Error: TELEGRAM_API_ID dan TELEGRAM_API_HASH harus disediakan via env var atau argumen CLI.",
            file=sys.stderr,
        )
        print("Contoh: python3 src/telegram_voip.py --api-id 12345 --api-hash 'abcdef...'")
        sys.exit(1)

    allowed_set = set(args.allow_user) if args.allow_user else set()

    agent = TelegramVoIPAgent(
        api_id=args.api_id,
        api_hash=args.api_hash,
        session_name=args.session,
        mode=args.mode,
        allowed_user_ids=allowed_set,
    )

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print("\nAplikasi dihentikan oleh pengguna.")


if __name__ == "__main__":
    main()
