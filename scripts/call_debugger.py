#!/usr/bin/env python3
"""
Call Debugger: Menangkap dan menampilkan semua update MTProto Telegram saat panggilan masuk.
"""
import asyncio
import os
import sys
import traceback
from dotenv import load_dotenv

import ntgcalls
from pyrogram import Client
from pyrogram.handlers import RawUpdateHandler
from pyrogram.raw import functions, types

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
api_hash = os.getenv("TELEGRAM_API_HASH", "")

if not api_id or not api_hash:
    print("Error: TELEGRAM_API_ID dan TELEGRAM_API_HASH harus disetel.", file=sys.stderr)
    sys.exit(1)


def to_ntg_rtc_server(conn):
    if isinstance(conn, types.PhoneConnectionWebrtc):
        return ntgcalls.RTCServer(
            id=conn.id, ipv4=conn.ip, ipv6=conn.ipv6, port=conn.port,
            username=conn.username, password=conn.password,
            turn=conn.turn, stun=conn.stun, tcp=False, peer_tag=None,
        )
    else:
        return ntgcalls.RTCServer(
            id=conn.id, ipv4=conn.ip, ipv6=conn.ipv6, port=conn.port,
            username=None, password=None, turn=False, stun=False,
            tcp=conn.tcp, peer_tag=conn.peer_tag,
        )


async def async_main():
    # Inisialisasi Client dan NTgCalls di dalam active event loop
    app = Client("userbot_session", api_id=api_id, api_hash=api_hash)
    ntg = ntgcalls.NTgCalls()
    active_call = {}
    loop = asyncio.get_running_loop()

    def on_ntg_sig(user_id, data):
        print(f"[NTgCalls Signaling OUT] Mengirim {len(data)} bytes ke Telegram...", flush=True)
        if "call_id" in active_call:
            peer = types.InputPhoneCall(id=active_call["call_id"], access_hash=active_call["access_hash"])
            async def send():
                try:
                    await app.invoke(functions.phone.SendSignalingData(peer=peer, data=data))
                    print("[NTgCalls Signaling OUT] Terkirim via MTProto.", flush=True)
                except Exception as e:
                    print(f"[NTgCalls Signaling OUT Error] {e}", flush=True)
            asyncio.run_coroutine_threadsafe(send(), loop)

    def on_ntg_conn(user_id, info):
        print("=" * 60, flush=True)
        print(f"[NTgCalls STATUS KONEKSI] User {user_id}: {info.state} ({info.kind})", flush=True)
        print("=" * 60, flush=True)

    def on_ntg_frames(user_id, mode, device, frames):
        print(f"[NTgCalls Audio Frame] Menerima {len(frames)} frames dari user {user_id}!", flush=True)

    ntg.on_signaling_data(on_ntg_sig)
    ntg.on_connection_change(on_ntg_conn)
    ntg.on_frames(on_ntg_frames)

    async def raw_update_handler(client, update, users, chats):
        up_name = type(update).__name__
        print(f"\n[Raw Update Masuk] -> {up_name}", flush=True)

        if isinstance(update, types.UpdatePhoneCall):
            call = update.phone_call
            c_name = type(call).__name__
            print(f"\n**************************************************", flush=True)
            print(f"*** EVENT TELEGRAM PHONE CALL: {c_name} ***", flush=True)
            print(f"**************************************************", flush=True)

            if isinstance(call, types.PhoneCallRequested):
                user_id = call.admin_id
                print(f"[CALL REQUESTED] Panggilan Masuk Dari User ID: {user_id}", flush=True)
                print(f"  - Call ID: {call.id}", flush=True)
                print(f"  - Access Hash: {call.access_hash}", flush=True)
                print(f"  - Protocol: min={call.protocol.min_layer}, max={call.protocol.max_layer}", flush=True)

                active_call["call_id"] = call.id
                active_call["access_hash"] = call.access_hash
                active_call["user_id"] = user_id

                try:
                    peer = types.InputPhoneCall(id=call.id, access_hash=call.access_hash)
                    print("[1] Mengirim phone.ReceivedCall (dering)...", flush=True)
                    await client.invoke(functions.phone.ReceivedCall(peer=peer))
                    print("    phone.ReceivedCall sukses!", flush=True)

                    print("[2] Mengambil DH Config...", flush=True)
                    dh = await client.invoke(functions.messages.GetDhConfig(version=0, random_length=256))
                    dh_config = ntgcalls.DhConfig(g=dh.g, p=dh.p, random=dh.random)

                    print("[3] Membuat P2P call di NTgCalls...", flush=True)
                    await ntg.create_p2p_call(user_id)
                    g_b = await ntg.init_exchange(user_id, dh_config, call.g_a_hash)
                    print(f"    g_b computed ({len(g_b)} bytes).", flush=True)

                    ntg_proto = ntg.get_protocol()
                    proto = types.PhoneCallProtocol(
                        min_layer=min(ntg_proto.min_layer, call.protocol.min_layer),
                        max_layer=min(ntg_proto.max_layer, call.protocol.max_layer),
                        udp_p2p=ntg_proto.udp_p2p and call.protocol.udp_p2p,
                        udp_reflector=ntg_proto.udp_reflector or call.protocol.udp_reflector,
                        library_versions=list(call.protocol.library_versions),
                    )
                    print(f"[4] Mengirim phone.AcceptCall...", flush=True)
                    res = await client.invoke(functions.phone.AcceptCall(peer=peer, g_b=g_b, protocol=proto))
                    print(f"    phone.AcceptCall BERHASIL! Status: {type(res.phone_call).__name__}", flush=True)

                except Exception as e:
                    print(f"[ERROR MENGANGKAT]: {e}", flush=True)
                    traceback.print_exc()

            elif isinstance(call, types.PhoneCall):
                print(f"[CALL ACTIVE] Handshake selesai! Menghubungkan WebRTC media...", flush=True)
                user_id = active_call.get("user_id", call.admin_id)
                try:
                    await ntg.exchange_keys(user_id, call.g_a_or_b, call.key_fingerprint)
                    servers = [to_ntg_rtc_server(c) for c in call.connections]
                    print(f"[5] Menghubungkan ke {len(servers)} WebRTC RTC servers...", flush=True)
                    await ntg.connect_p2p(
                        user_id,
                        servers,
                        list(call.protocol.library_versions),
                        p2p_allowed=True,
                        custom_parameters=None,
                    )
                    audio_desc = ntgcalls.AudioDescription(
                        media_source=ntgcalls.MediaSource.EXTERNAL,
                        sample_rate=48000,
                        channel_count=1,
                        input="",
                        keep_open=True,
                    )
                    media = ntgcalls.MediaDescription(audio_desc, None, None, None)
                    await ntg.set_stream_sources(user_id, ntgcalls.StreamMode.CAPTURE, media)
                    await ntg.set_stream_sources(user_id, ntgcalls.StreamMode.PLAYBACK, media)
                    print("    MEDIA PIPELINE AKTIF! Suara penelpon terhubung.", flush=True)
                except Exception as e:
                    print(f"[ERROR MEDIA CONNECT]: {e}", flush=True)
                    traceback.print_exc()

            elif isinstance(call, types.PhoneCallDiscarded):
                reason = type(call.reason).__name__ if call.reason else "Normal"
                print(f"[CALL DISCARDED] Panggilan selesai. Alasan: {reason}", flush=True)
                if "user_id" in active_call:
                    try:
                        await ntg.stop(active_call["user_id"])
                    except Exception:
                        pass
                    active_call.clear()

        elif isinstance(update, types.UpdatePhoneCallSignalingData):
            print(f"[Signaling IN] Diterima {len(update.data)} bytes untuk Call ID {update.phone_call_id}", flush=True)
            if "user_id" in active_call:
                try:
                    await ntg.send_signaling_data(active_call["user_id"], update.data)
                except Exception as e:
                    print(f"[ERROR send_signaling_data IN]: {e}", flush=True)

    # Register handler langsung ke Pyrogram
    app.add_handler(RawUpdateHandler(raw_update_handler))

    print("Memulai koneksi Telegram Client...", flush=True)
    await app.start()
    me = await app.get_me()
    print("=" * 60, flush=True)
    print(f"Debugger Aktif & Mendengarkan Update!", flush=True)
    print(f"Akun Bot: {me.first_name} (@{me.username or 'No Username'}, ID: {me.id})")
    print(f"Dispatcher Handlers: {len(app.dispatcher.groups.get(0, []))} handler terpasang.")
    print(f"SILAKAN TELEPON AKUN INI SEKARANG.")
    print("=" * 60, flush=True)

    # Biarkan event loop berjalan
    await asyncio.Event().wait()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nDebugger dihentikan.")


if __name__ == "__main__":
    main()
