#!/usr/bin/env python3
"""
Regression test untuk bug "audio AI tersendat / terpotong".

Akar masalah: `_telegram_audio_sender_worker` lama BERHENTI mengirim frame
saat antrean kosong atau saat menunggu pre-buffer 250 ms. Karena `ntgcalls`
AudioSink menaruh frame tiap 10 ms, berhenti mengirim membuat jitter buffer
WebRTC di sisi penelpon underrun -> suara tersendat/patah.

Test ini memastikan:
1. Saat antrean kosong, sender TETAP mengirim frame SENYAP pada cadence ~10 ms.
2. Audio jawaban yang masuk antrean dikirim lengkap dan berurutan (tidak dibuang).
"""
import asyncio
import statistics
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import CallSession, SessionState, TG_FRAME_BYTES

SILENCE = b"\x00" * TG_FRAME_BYTES


class FakeNtg:
    def __init__(self):
        self.frames = []  # list[tuple[bytes, float]]

    async def send_external_frame(self, user_id, device, data, frame_data):
        self.frames.append((bytes(data), time.monotonic()))


def _make_session(ntg):
    session = CallSession(user_id=1, call_id=1, access_hash=1, agent=SimpleNamespace(ntg=ntg))
    session.state = SessionState.ACTIVE
    session.is_greeting = False
    return session


class TestTelegramAudioSender(unittest.IsolatedAsyncioTestCase):
    async def test_kirim_senyap_terus_menerus_saat_antrean_kosong(self):
        ntg = FakeNtg()
        session = _make_session(ntg)
        task = asyncio.create_task(session._telegram_audio_sender_worker())
        await asyncio.sleep(0.16)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Kode LAMA nyaris tidak mengirim apa pun saat antrean kosong.
        # Kode BARU tetap mengirim senyap pada cadence ~100 frame/detik.
        self.assertGreaterEqual(
            len(ntg.frames), 8, "Sender harus tetap mengirim frame walau antrean kosong"
        )
        self.assertTrue(
            all(data == SILENCE for data, _ in ntg.frames),
            "Isi frame harus senyap saat antrean kosong",
        )

        gaps = [t2 - t1 for (_, t1), (_, t2) in zip(ntg.frames, ntg.frames[1:])]
        median_gap = statistics.median(gaps)
        self.assertGreater(median_gap, 0.005, f"Pengiriman terlalu cepat (median {median_gap:.4f}s)")
        self.assertLess(median_gap, 0.018, f"Pengiriman terlalu lambat/tersendat (median {median_gap:.4f}s)")

    async def test_memutar_audio_jawaban_lengkap_dan_berurutan(self):
        ntg = FakeNtg()
        session = _make_session(ntg)
        task = asyncio.create_task(session._telegram_audio_sender_worker())
        await asyncio.sleep(0.03)

        payload = [i.to_bytes(2, "little") * (TG_FRAME_BYTES // 2) for i in range(1, 26)]
        for frame in payload:
            session.tg_out_queue.put_nowait(frame)

        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        sent_audio = [data for data, _ in ntg.frames if data != SILENCE]
        self.assertEqual(
            sent_audio,
            payload,
            "Audio jawaban harus terkirim lengkap dan berurutan tanpa ada yang dibuang",
        )


if __name__ == "__main__":
    unittest.main()
