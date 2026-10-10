#!/usr/bin/env python3
"""
Regression test untuk bug "AI tidak merespons setelah sapaan".

Akar masalah: `google.genai` `session.receive()` hanya mengembalikan SATU
giliran model lalu berhenti begitu `turn_complete=True` (lihat
`google/genai/live.py`). Test ini memakai sesi Gemini tiruan yang meniru
perilaku tersebut dan memastikan `CallSession._gemini_receiver_worker`
tetap memproses audio dari giliran KEDUA dan seterusnya.
"""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.main import CallSession, SessionState, TG_FRAME_BYTES


class FakeGeminiSession:
    """Meniru `AsyncSession.receive()`: satu generator per giliran, berhenti di turn_complete."""

    def __init__(self, turns):
        self._turns = turns
        self._idx = 0

    def receive(self):
        return self._gen()

    async def _gen(self):
        if self._idx < len(self._turns):
            turn = self._turns[self._idx]
            self._idx += 1
            for message in turn:
                yield message
            return
        # Tidak ada giliran lagi -> tetap "menganggur" seperti WebSocket diam.
        await asyncio.Event().wait()


def _model_turn(pcm_bytes):
    return SimpleNamespace(parts=[SimpleNamespace(inline_data=SimpleNamespace(data=pcm_bytes))])


def _message(model_turn=None, turn_complete=False):
    return SimpleNamespace(
        server_content=SimpleNamespace(
            input_transcription=None,
            output_transcription=None,
            interrupted=False,
            model_turn=model_turn,
            turn_complete=turn_complete,
        )
    )


class TestGeminiReceiverMultiTurn(unittest.IsolatedAsyncioTestCase):
    async def test_memproses_beberapa_giliran(self):
        # 600 sampel 24 kHz -> 1200 sampel 48 kHz = 2400 byte per giliran.
        # TG_FRAME_BYTES = 960 byte, jadi dua giliran menghasilkan total 5 frame.
        pcm_24k = np.arange(600, dtype=np.int16).tobytes()
        turns = [
            [_message(_model_turn(pcm_24k)), _message(turn_complete=True)],
            [_message(_model_turn(pcm_24k)), _message(turn_complete=True)],
        ]
        expected_frames = 2 * (2400 // TG_FRAME_BYTES) + 1  # 5 frame (lihat buffer carry-over)

        session = CallSession(user_id=1, call_id=1, access_hash=1, agent=SimpleNamespace(ntg=None))
        session.state = SessionState.ACTIVE
        session.is_greeting = False
        session.gemini_session = FakeGeminiSession(turns)

        task = asyncio.create_task(session._gemini_receiver_worker())
        try:
            for _ in range(100):
                if session.tg_out_queue.qsize() >= expected_frames:
                    break
                await asyncio.sleep(0.02)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Bila `receive()` tidak dipanggil ulang per giliran, hanya ~2 frame dari
        # giliran pertama yang akan terkumpul dan test ini gagal.
        self.assertEqual(
            session.tg_out_queue.qsize(),
            expected_frames,
            f"Diharapkan {expected_frames} frame dari 2 giliran, dapat {session.tg_out_queue.qsize()}",
        )


if __name__ == "__main__":
    unittest.main()
