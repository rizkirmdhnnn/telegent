"""Unit test pengirim audio ber-cadence (anti-stutter)."""

from __future__ import annotations

import asyncio
import statistics

from helpers import FakeSink

from telegent.audio.cadence import run_cadence_sender

SILENCE = b"\x00" * 960


async def _run(sink, source, *, duration: float, prefill: int = 15, send=None) -> None:
    active = [True]
    task = asyncio.create_task(
        run_cadence_sender(
            sink=sink,
            source=source,
            is_active=lambda: active[0],
            frame_bytes=960,
            interval=0.010,
            prefill_frames=prefill,
            send=send,
        )
    )
    await asyncio.sleep(duration)
    active[0] = False
    await asyncio.wait_for(task, timeout=1.0)


async def test_silence_fill_ketika_antrean_kosong():
    sink = FakeSink()
    source: asyncio.Queue = asyncio.Queue(maxsize=100)
    await _run(sink, source, duration=0.16)

    assert len(sink.frames) >= 8, "harus tetap mengirim frame walau antrean kosong"
    assert all(frame == SILENCE for frame in sink.frames)
    # ~100 frame/detik -> dalam 160 ms sekitar 16 frame (beri toleransi).
    assert 8 <= len(sink.frames) <= 40


async def test_memutar_audio_berurutan_tanpa_dibuang():
    sink = FakeSink()
    source: asyncio.Queue = asyncio.Queue(maxsize=100)
    payload = [i.to_bytes(2, "little") * 480 for i in range(1, 26)]
    for frame in payload:
        source.put_nowait(frame)

    await _run(sink, source, duration=0.5, prefill=15)

    sent_audio = [frame for frame in sink.frames if frame != SILENCE]
    assert sent_audio == payload


async def test_median_interval_mendekati_10ms():
    times: list[float] = []

    async def recording_send(frame: bytes) -> None:
        times.append(asyncio.get_event_loop().time())

    sink = FakeSink()
    source: asyncio.Queue = asyncio.Queue(maxsize=100)
    await _run(sink, source, duration=0.3, prefill=15, send=recording_send)

    gaps = [b - a for a, b in zip(times, times[1:])]
    assert gaps
    median = statistics.median(gaps)
    assert 0.005 < median < 0.018, f"median interval {median:.4f}s tidak wajar"
