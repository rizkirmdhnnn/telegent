"""Tes regresi untuk temuan review Fase 3 (tiket E1/E2).

Tiap pengujian mengunci satu perilaku yang sebelumnya salah: event ganda, race
`call.ended`, filter tanggal salah zona, `store_transcripts` yang tak berlaku, dan
`runtime.error` yang tak pernah terbit.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from web_helpers import csrf_of, do_setup

from telegent.app import TelegentApp
from telegent.config import Settings
from telegent.web import call_store
from telegent.web.call_recorder import CallRecorder
from telegent.web.db.base import Database
from telegent.web.events import EventBus
from telegent.web.settings_store import SettingsStore

_PHONE = "+6281234567890"


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        telegram_api_id=1,
        telegram_api_hash="h",
        gemini_api_key="k",
        _env_file=None,  # type: ignore[call-arg]
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _events(bus: EventBus) -> list[tuple[str, dict]]:
    return [(event.type, event.data) for event in bus.history()]


# --------------------------------------------------- [_BUG] event tak ganda


async def test_event_panggilan_terbit_tepat_sekali(
    database: Database, tmp_path: Path
) -> None:
    """Dengan `CallRecorder` terpasang, tiap kejadian dikirim SATU kali ke bus."""
    bus = EventBus()
    recorder = CallRecorder(database, bus=bus)
    recorder.start()

    app = TelegentApp(
        _settings(allowed_user_ids="7", max_calls_per_window=0),
        install_signal_handlers=False,
        call_observer=recorder,
        event_sink=bus.publish,
    )

    async def fake_discard(call, reason, user_id): ...

    app._discard_call = fake_discard  # type: ignore[assignment]
    await app._handle_call_requested(SimpleNamespace(id=1, access_hash=1, admin_id=999))

    nama = [nama for nama, _ in _events(bus)]
    assert nama.count("call.incoming") == 1, "call.incoming terbit lebih dari sekali"
    assert nama.count("call.ended") == 1, "call.ended terbit lebih dari sekali"

    await recorder.aclose()


async def test_event_tetap_terbit_tanpa_recorder(tmp_path: Path) -> None:
    """Tanpa observer, `_emit_call` tetap menjadi jalan keluar (tanpa event hilang)."""
    bus = EventBus()
    app = TelegentApp(
        _settings(allowed_user_ids="7", max_calls_per_window=0),
        install_signal_handlers=False,
        event_sink=bus.publish,
    )

    async def fake_discard(call, reason, user_id): ...

    app._discard_call = fake_discard  # type: ignore[assignment]
    await app._handle_call_requested(SimpleNamespace(id=1, access_hash=1, admin_id=999))

    nama = [nama for nama, _ in _events(bus)]
    assert "call.incoming" in nama and "call.ended" in nama


# -------------------------------------------------- [_BUG] race call.ended


async def test_call_ended_hanya_sekali_saat_ada_duplicate_discard(tmp_path: Path) -> None:
    """`hangup()` dan handler discarded bisa berebut sesi; `call.ended` tetap satu."""
    bus = EventBus()
    app = TelegentApp(
        _settings(max_calls_per_window=0),
        install_signal_handlers=False,
        event_sink=bus.publish,
    )
    class _Session:
        user_id = 5
        call_id = 1
        access_hash = 1
        duration_seconds = 7
        end_reason = None

        async def close(self) -> None:
            return None

    hangup = app._make_hangup(_Session())  # type: ignore[arg-type]
    app.sessions[5] = _Session()  # type: ignore[assignment]

    await app._handle_call_discarded(SimpleNamespace(id=1))
    await hangup()

    assert [nama for nama, _ in _events(bus)].count("call.ended") == 1


# ------------------------------------------------ [_BUG] filter salah zona


def test_parse_dt_mengonversi_ke_utc_bukan_waktu_lokal() -> None:
    from telegent.web.routers.calls import _parse_dt

    tengah_malam_utc = datetime(2026, 1, 1, 0, 0)
    hasil = _parse_dt("2026-01-01T00:00:00Z", field="from")
    assert hasil ==tengah_malam_utc, "waktu dengan zona harus dinormalkan ke UTC"
    assert hasil.tzinfo is None

    # Tanpa zona waktu: dianggap sudah UTC (tidak digeser).
    assert _parse_dt("2026-01-01T00:00:00", field="from") ==tengah_malam_utc


def test_parse_dt_menolak_tanggal_asing() -> None:
    from telegent.web.errors import APIError
    from telegent.web.routers.calls import _parse_dt

    with pytest.raises(APIError) as exc:
        _parse_dt("bukan-tanggal", field="from")
    assert exc.value.code == "invalid_filter"


# ------------------------------------------ [_BUG] store_transcripts tak_apply


def test_store_transcripts_berlaku_langsung(live_client: TestClient) -> None:
    """Registry menandai `hot`, jadi toggle harus berlaku tanpa restart (Q13)."""
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}
    recorder = live_client.app.state.call_recorder
    assert recorder.store_transcripts is True

    resp = live_client.put(
        "/api/settings", json={"changes": {"store_transcripts": False}}, headers=headers
    )
    assert resp.status_code == 200
    assert "store_transcripts" in resp.json()["applied"]
    assert recorder.store_transcripts is False, "toggle tidak berlaku tanpa restart"

    live_client.put(
        "/api/settings", json={"changes": {"store_transcripts": True}}, headers=headers
    )
    assert recorder.store_transcripts is True


# ------------------------------------------------- [_BUG] runtime.error kosong


async def test_runtime_error_terbit_saat_start_gagal(
    store: SettingsStore, tmp_path: Path
) -> None:
    from telegent.web.runtime import RuntimeController

    events: list[tuple[str, dict]] = []

    class _Failing:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        async def start(self) -> None:
            raise RuntimeError("kredensial ditolak")

    await store.update(
        {
            "telegram_api_id": 1,
            "telegram_api_hash": "0" * 32,
            "gemini_api_key": "AIzaSy0123456789012345678901234567890",
        }
    )
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "userbot_session.session").write_bytes(b"x")

    controller = RuntimeController(
        store,
        app_factory=lambda s: _Failing(s),  # type: ignore[arg-type,return-value]
        session_dir=sessions,
        event_sink=lambda nama, payload: events.append((nama, payload)),
    )

    status = await controller.start()

    assert status.state.value == "error"
    nama = [nama for nama, _ in events]
    # `status` terbit lebih dulu (transisi STARTING), lalu `runtime.error`.
    assert nama == ["status", "runtime.error"]
    assert events[-1][1]["message"]


async def test_status_event_terbit_setelah_berhenti(store: SettingsStore, tmp_path: Path) -> None:
    from telegent.web.runtime import RuntimeController

    events: list[tuple[str, dict]] = []

    class _Running:
        instances: list["_Running"] = []

        def __init__(self, settings: Settings) -> None:
            self.settings = settings
            self._stop = __import__("asyncio").Event()
            self.sessions: dict[int, Any] = {}
            _Running.instances.append(self)

        def active_sessions(self) -> list[Any]:
            return list(self.sessions.values())

        async def start(self) -> None: ...

        async def stop(self) -> None:
            self._stop.set()

        async def wait_stopped(self) -> None:
            await self._stop.wait()

        async def shutdown(self) -> None: ...

        def set_settings(self, settings: Settings) -> None:
            self.settings = settings

        def status_payload(self) -> dict:
            return {"running": True, "active_calls": 0, "model": "m", "logged_in_user": None}

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "userbot_session.session").write_bytes(b"x")

    await store.update(
        {
            "telegram_api_id": 1,
            "telegram_api_hash": "0" * 32,
            "gemini_api_key": "AIzaSy0123456789012345678901234567890",
        }
    )
    controller = RuntimeController(
        store,
        app_factory=lambda s: _Running(s),  # type: ignore[arg-type,return-value]
        session_dir=sessions,
        event_sink=lambda nama, payload: events.append((nama, payload)),
    )

    await controller.start()
    await controller.stop()

    assert [nama for nama, _ in events].count("status") >= 2, "status tidak disiarkan"


# ------------------------------------- [_BUG] started_at tidak digeser


async def test_started_at_digeser_agar_konsisten_dengan_durasi(
    database: Database, store: SettingsStore, tmp_path: Path
) -> None:
    """`ended_at - started_at` harus sama dengan `duration_sec` (§5.5)."""
    await store.update(
        {
            "telegram_api_id": 1,
            "telegram_api_hash": "0" * 32,
            "gemini_api_key": "AIzaSy0123456789012345678901234567890",
        }
    )
    recorder = CallRecorder(database)
    recorder.start()

    recorder.call_incoming(7, 555, user_display=None)
    await recorder.flush()
    await asyncio.sleep(0)  # izinkan satu giliran event loop
    dibuat = (await call_store.get_call(database, 1)).started_at

    recorder.call_started(7, 555)
    recorder.session_event(7, "transcript", {"speaker": "caller", "text": "halo"})
    recorder.call_ended(7, 555, outcome="answered", end_reason="caller_hangup", duration_sec=0)
    await recorder.flush()
    await recorder.aclose()

    detail = await call_store.get_call(database, 1)
    assert detail is not None
    assert detail.ended_at is not None
    assert detail.started_at >= dibuat, "started_at tidak digeser ke waktu panggilan aktif"
    assert detail.duration_sec == 0
    # Durasi dihitung dari `started_at` yang sudah digeser, jadi konsisten.
    assert int((detail.ended_at - detail.started_at).total_seconds()) == 0


# ------------------------------------------------- status payload §7


async def test_status_payload_memiliki_state() -> None:
    app = TelegentApp(_settings(), install_signal_handlers=False)
    payload = app.status_payload()
    assert payload["state"] == "stopped"
    assert "running" in payload and "active_calls" in payload


import asyncio  # noqa: E402  (dipakai di beberapa pengujian async)