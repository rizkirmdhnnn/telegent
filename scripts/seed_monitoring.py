"""Seed basis data-phase 3 untuk verifikasi manual panel.

Membuat `call_record` + transkrip + tool call contoh supaya halaman Panggilan
dan Log bisa diperiksa tanpa menunggu panggilan Telegram sungguhan.

    uv run python scripts/seed_monitoring.py data/telegent.db
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from telegent.web.call_recorder import build_recorder  # noqa: E402
from telegent.web.crypto import SecretCipher  # noqa: E402
from telegent.web.db import models  # noqa: E402
from telegent.web.db.base import Database, utcnow  # noqa: E402
from telegent.web.db.migrate import upgrade_to_head_async  # noqa: E402
from telegent.web.events import EventBus  # noqa: E402
from telegent.web.log_stream import BusLogHandler, LogRingBuffer  # noqa: E402
from telegent.web.settings_store import SettingsStore  # noqa: E402

#: (nama panggilan, user_id, outcome, end_reason, durasi, baris transkrip, tool)
#: `args` berupa dict (bukan string JSON) — `CallRecorder` yang berserialkan.
_SAMPLES = [
    (
        "@budi | Pemeriksaan reservasi hotel",
        5550001,
        "answered",
        "caller_hangup",
        96,
        [
            ("caller", "Halo, apakah masih ada kamar untuk tanggal 12?"),
            ("ai", "Selamat siang. Untuk tanggal 12 masih tersedia. Bisakah sebutkan nama pemesan?"),
            ("caller", "Budi Santoso, dua kamar."),
            ("ai", "Baik, dua kamar untuk tanggal 12. Saya catat dulu ya."),
            ("caller", "Terima kasih, tolong kirim konfirmasi ke email saya."),
        ],
        [("get_current_datetime", {"timezone": "Asia/Jakarta"}, "ok", 12)],
    ),
    (
        "@sinta | Cek jam operasional",
        5550002,
        "answered",
        "ai_end_call",
        22,
        [
            ("caller", "Buka sampai jam berapa hari ini?"),
            ("ai", "Buka sampai pukul 21.00 setiap hari."),
            ("caller", "Oke, makasih. Sampai jumpa."),
        ],
        [("get_current_datetime", {"timezone": "Asia/Jakarta"}, "ok", 9)],
    ),
    (
        "@asing | Penelpon di luar whitelist",
        9999999,
        "rejected_whitelist",
        "rejected",
        0,
        [],
        [],
    ),
    (
        "@spam | Nomor salah (rate-limit)",
        5550003,
        "rejected_ratelimit",
        "rejected",
        0,
        [],
        [],
    ),
]


async def seed(db_url: str) -> None:
    await upgrade_to_head_async(db_url)
    db = Database(db_url)
    data_dir = Path(db_url).resolve().parent
    store = SettingsStore(db, SecretCipher.for_data_dir(data_dir / ".secret_key"))
    bus = EventBus()

    import logging

    BusLogHandler(bus, LogRingBuffer(maxlen=500)).setLevel(logging.INFO)
    for name in ("telegent.web", "telegent.app", "telegent.call"):
        logging.getLogger(name).info("Panel pemantauan siap — await %s.", name)

    recorder = await build_recorder(db, store, bus=bus)

    # Bersihkan data lama supaya hasil seeding deterministik.
    async with db.session() as session:
        for row in (
            await session.execute(select(models.TranscriptEntry))
        ).scalars().all():
            await session.delete(row)
        for row in (await session.execute(select(models.ToolCallRecord))).scalars().all():
            await session.delete(row)
        for row in (await session.execute(select(models.CallRecord))).scalars().all():
            await session.delete(row)

    for index, (
        label,
        user_id,
        outcome,
        end_reason,
        duration,
        transcript,
        tools,
    ) in enumerate(_SAMPLES):
        call_id = 9000 + index
        recorder.call_incoming(call_id, user_id, user_display=label)
        if outcome == "answered":
            recorder.call_started(call_id, user_id)
            for speaker, text in transcript:
                recorder.session_event(call_id, "transcript", {"speaker": speaker, "text": text})
            for name, args, status, duration_ms in tools:
                recorder.session_event(
                    call_id,
                    "tool_call",
                    {
                        "name": name,
                        "args": args,
                        "result": {"output": {"iso": "2026-01-12T09:00:00+07:00"}},
                        "status": status,
                        "duration_ms": duration_ms,
                    },
                )
        recorder.call_ended(
            call_id,
            user_id,
            outcome=outcome,
            end_reason=end_reason,
            duration_sec=duration,
        )

    await recorder.aclose()

    # Majukan satu panggilan agar bisa diuji tombol hangup dari panel.
    async with db.session() as session:
        row = models.CallRecord(
            tg_call_id=9100,
            user_id=5550004,
            user_display="@live",
            outcome="pending",
            started_at=utcnow() - timedelta(seconds=42),
        )
        session.add(row)

    await db.dispose()
    print(f"Seed selesai: {len(_SAMPLES) + 1} panggilan pada {db_url}")


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "data/telegent.db"
    path = Path(target).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(seed(f"sqlite+aiosqlite:///{path.as_posix()}"))


if __name__ == "__main__":
    main()