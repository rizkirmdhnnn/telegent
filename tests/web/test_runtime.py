"""Test lifecycle TelegentApp & RuntimeController (tiket A7)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from telegent.app import TelegentApp
from telegent.config import Settings
from telegent.web.runtime import RuntimeController, RuntimeState

_CREDENTIALS = {
    "telegram_api_id": 12345678,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        telegram_api_id=1,
        telegram_api_hash="h",
        gemini_api_key="k",
        _env_file=None,  # type: ignore[call-arg]
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ----------------------------------------------------------------- fake natives


class _FakeClient:
    instances: list["_FakeClient"] = []

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.started = False
        self.stopped = False
        self.handlers: list[Any] = []
        _FakeClient.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def get_me(self) -> Any:
        return SimpleNamespace(id=99, first_name="Bot", username="bot")

    def add_handler(self, handler: Any) -> None:
        self.handlers.append(handler)


class _FakeNtgCalls:
    def __init__(self) -> None:
        self.stopped: list[int] = []

    def on_signaling_data(self, *_a: Any) -> None: ...
    def on_connection_change(self, *_a: Any) -> None: ...
    def on_frames(self, *_a: Any) -> None: ...

    async def stop(self, user_id: int) -> None:
        self.stopped.append(user_id)


@pytest.fixture
def native_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("telegent.app.Client", _FakeClient)
    monkeypatch.setattr("telegent.app.ntgcalls.NTgCalls", _FakeNtgCalls)
    monkeypatch.setattr(
        "telegent.app.genai.Client", lambda api_key=None: SimpleNamespace(api_key=api_key)
    )
    _FakeClient.instances.clear()


# ------------------------------------------------------- TelegentApp lifecycle


async def test_start_shutdown_dan_status(native_fakes: None) -> None:
    app = TelegentApp(_settings(), install_signal_handlers=False)

    assert app.is_running is False
    await app.start()

    assert app.is_running is True
    assert app.me.id == 99
    payload = app.status_payload()
    assert payload["running"] is True
    assert payload["logged_in_user"]["username"] == "bot"
    assert payload["model"] == app.settings.gemini_model

    await app.stop()
    await app.shutdown()
    assert app.is_running is False
    assert _FakeClient.instances[0].stopped is True


async def test_start_dua_kali_tidak_menggandakan_klien(native_fakes: None) -> None:
    app = TelegentApp(_settings(), install_signal_handlers=False)
    await app.start()
    await app.start()
    assert len(_FakeClient.instances) == 1
    await app.shutdown()


async def test_shutdown_idempoten(native_fakes: None) -> None:
    app = TelegentApp(_settings(), install_signal_handlers=False)
    await app.start()
    await app.shutdown()
    await app.shutdown()  # tidak boleh error


async def test_stop_membuat_wait_stopped_selesai(native_fakes: None) -> None:
    app = TelegentApp(_settings(), install_signal_handlers=False)
    await app.start()

    waiter = asyncio.create_task(app.wait_stopped())
    await asyncio.sleep(0)
    assert not waiter.done()

    await app.stop()
    await asyncio.wait_for(waiter, timeout=1)


async def test_serve_berhenti_dan_mematikan_klien(native_fakes: None) -> None:
    app = TelegentApp(_settings(), install_signal_handlers=False)
    task = asyncio.create_task(app.serve())
    await asyncio.sleep(0.01)

    assert app.is_running is True
    await app.stop()
    await asyncio.wait_for(task, timeout=2)
    assert _FakeClient.instances[0].stopped is True


async def test_set_settings_memperbarui_rate_limiter() -> None:
    app = TelegentApp(_settings(max_calls_per_window=1, call_window_seconds=60))
    assert app.rate_limiter.allow(5) is True
    assert app.rate_limiter.allow(5) is False

    app.set_settings(_settings(max_calls_per_window=5, call_window_seconds=60))
    assert app.rate_limiter.allow(5) is True


async def test_event_sink_menerima_event(native_fakes: None) -> None:
    events: list[tuple[str, dict]] = []
    app = TelegentApp(
        _settings(),
        install_signal_handlers=False,
        event_sink=lambda name, payload: events.append((name, payload)),
    )
    await app.start()
    assert events[0][0] == "status"
    assert events[0][1]["running"] is True
    await app.shutdown()


async def test_event_sink_yang_gagal_tidak_mengganggu(native_fakes: None) -> None:
    def boom(_name: str, _payload: dict) -> None:
        raise RuntimeError("monitor mati")

    app = TelegentApp(_settings(), install_signal_handlers=False, event_sink=boom)
    await app.start()  # tidak boleh melempar
    assert app.is_running is True
    await app.shutdown()


async def test_event_sink_mencatat_penolakan(native_fakes: None) -> None:
    events: list[tuple[str, dict]] = []
    app = TelegentApp(
        _settings(allowed_user_ids="7", max_calls_per_window=0),
        install_signal_handlers=False,
        event_sink=lambda name, payload: events.append((name, payload)),
    )

    async def fake_discard(call, reason, user_id): ...

    app._discard_call = fake_discard  # type: ignore[assignment]
    await app._handle_call_requested(SimpleNamespace(id=1, access_hash=1, admin_id=999))

    assert events[-1][0] == "call.ended"
    assert events[-1][1]["outcome"] == "rejected_whitelist"


# --------------------------------------------------------- RuntimeController


class _FakeTelegent:
    """Pengganti TelegentApp untuk pengujian controller."""

    created: list["_FakeTelegent"] = []
    fail_start = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.running = False
        self.closed = False
        self.stop_event = asyncio.Event()
        self.active_calls = 0
        self.sessions: dict[int, Any] = {}
        _FakeTelegent.created.append(self)

    def active_sessions(self) -> list[Any]:
        """Sesi aktif (dibuang saat panggilan selesai) — sama seperti TelegentApp."""
        return list(self.sessions.values())

    async def start(self) -> None:
        if _FakeTelegent.fail_start:
            raise RuntimeError("kredensial ditolak")
        self.running = True

    async def stop(self) -> None:
        self.running = False
        self.stop_event.set()

    async def wait_stopped(self) -> None:
        await self.stop_event.wait()

    async def shutdown(self) -> None:
        self.closed = True
        self.running = False

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings

    def status_payload(self) -> dict:
        return {
            "running": self.running,
            "active_calls": self.active_calls,
            "model": self.settings.gemini_model,
            "logged_in_user": {"id": 99, "first_name": "Bot", "username": "bot"},
        }


@pytest.fixture
def controller_factory(tmp_path: Path):
    _FakeTelegent.created.clear()
    _FakeTelegent.fail_start = False

    def make(store: Any) -> RuntimeController:
        return RuntimeController(
            store,
            app_factory=lambda settings: _FakeTelegent(settings),  # type: ignore[arg-type,return-value]
            session_dir=tmp_path / "sessions",
        )

    return make


def _make_session(tmp_path: Path, name: str = "userbot_session") -> None:
    directory = tmp_path / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.session").write_bytes(b"fake")


async def test_start_menolak_bila_konfigurasi_kurang(store, controller_factory) -> None:
    controller = controller_factory(store)
    status = await controller.start()

    assert status.state is RuntimeState.NOT_CONFIGURED
    assert status.running is False
    assert status.last_error
    assert _FakeTelegent.created == []


async def test_start_menolak_bila_belum_login(store, controller_factory) -> None:
    await store.update(_CREDENTIALS)
    controller = controller_factory(store)

    status = await controller.start()
    assert status.state is RuntimeState.NEEDS_LOGIN
    assert "login" in (status.last_error or "").lower()
    assert _FakeTelegent.created == []


async def test_start_dan_stop(store, controller_factory, tmp_path: Path) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)

    status = await controller.start()
    assert status.state is RuntimeState.RUNNING
    assert status.running is True
    assert status.model
    assert status.logged_in_user == {"id": 99, "first_name": "Bot", "username": "bot"}
    assert status.since is not None

    after = await controller.stop()
    assert after.state is RuntimeState.STOPPED
    assert after.running is False
    assert controller.app is None
    assert _FakeTelegent.created[0].closed is True


async def test_start_kedua_tidak_membuat_instance_baru(
    store, controller_factory, tmp_path: Path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)

    await controller.start()
    await controller.start()
    assert len(_FakeTelegent.created) == 1
    await controller.stop()


async def test_restart_membuat_instance_baru(
    store, controller_factory, tmp_path: Path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)

    await controller.start()
    status = await controller.restart()

    assert status.state is RuntimeState.RUNNING
    assert len(_FakeTelegent.created) == 2
    assert _FakeTelegent.created[0].closed is True
    await controller.stop()


async def test_gagal_start_menjadi_error(
    store, controller_factory, tmp_path: Path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    _FakeTelegent.fail_start = True
    controller = controller_factory(store)

    status = await controller.start()
    assert status.state is RuntimeState.ERROR
    assert "kredensial ditolak" in (status.last_error or "")
    assert controller.app is None


async def test_status_saat_berhenti(store, controller_factory) -> None:
    controller = controller_factory(store)
    status = controller.status()
    assert status.state is RuntimeState.STOPPED
    assert status.active_calls == 0
    assert status.to_dict()["state"] == "stopped"


async def test_refresh_settings_live_apply(
    store, controller_factory, tmp_path: Path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    await store.update({"max_concurrent_calls": 9})
    status = await controller.refresh_settings()

    assert _FakeTelegent.created[0].settings.max_concurrent_calls == 9
    assert status.pending_restart == []
    await controller.stop()


async def test_perubahan_kredensial_menunggu_restart(
    store, controller_factory, tmp_path: Path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    await store.update({"gemini_api_key": "AIzaBaru012345678901234567890"})
    status = await controller.refresh_settings()
    assert status.pending_restart == ["gemini_api_key"]

    # Belum dijalankan ulang; konfigurasi masih yang lama.
    assert _FakeTelegent.created[0].settings.gemini_api_key != "AIzaBaru012345678901234567890"

    applied = await controller.apply_pending()
    assert applied.state is RuntimeState.RUNNING
    assert len(_FakeTelegent.created) == 2
    assert applied.pending_restart == []
    assert (
        _FakeTelegent.created[1].settings.gemini_api_key == "AIzaBaru012345678901234567890"
    )
    await controller.stop()


async def test_apply_pending_tanpa_perubahan_hanya_refresh(
    store, controller_factory, tmp_path: Path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    await controller.apply_pending()
    assert len(_FakeTelegent.created) == 1  # tidak restart
    await controller.stop()


async def test_setting_restart_tidak_diapply_langsung(
    store, controller_factory, tmp_path: Path
) -> None:
    """Nilai kelas restart tetap dipakai yang lama sampai bot di-restart."""
    await store.update({**_CREDENTIALS, "max_concurrent_calls": 3})
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    await store.update({"max_concurrent_calls": 11})  # hot
    await store.update({"telegram_session_name": "sesi_baru"})  # restart
    await controller.refresh_settings()

    runtime = _FakeTelegent.created[0]
    assert runtime.settings.max_concurrent_calls == 11  # hot terpasang
    assert runtime.settings.telegram_session_name == "userbot_session"  # belum berubah
    await controller.stop()


async def test_stop_saat_tidak_running_aman(store, controller_factory) -> None:
    controller = controller_factory(store)
    status = await controller.stop()
    assert status.state is RuntimeState.STOPPED


# ------------------------------------------------------------- graceful drain


class _FakeSession:
    """Sesi palsu: `auto_close=False` berarti tidak pernah selesai sendiri.

    `registry` adalah dict `app.sessions`; saat panggilan selesai, sesi dibuang
    dari sana — meniru callback `on_stop` pada `TelegentApp`.
    """

    def __init__(self, *, registry: dict[int, Any], auto_close: bool = True) -> None:
        self.user_id = 42
        self.registry = registry
        self.auto_close = auto_close
        self.hangup_reasons: list[str] = []
        self.closed = False

    def schedule_hangup(self, min_wait: float = 0.0, *, reason: str) -> None:
        self.hangup_reasons.append(reason)
        if self.auto_close:
            self.registry.pop(self.user_id, None)
            self.closed = True

    async def close(self) -> None:
        self.closed = True
        self.registry.pop(self.user_id, None)


async def test_stop_mendrain_panggilan_aktif(store, controller_factory, tmp_path: Path) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    session = _FakeSession(registry=controller.app.sessions)  # type: ignore[attr-defined]
    controller.app.sessions[42] = session  # type: ignore[attr-defined]
    status = await controller.stop()

    assert session.hangup_reasons == ["panel_hangup"]
    assert controller.last_drained == 1
    assert status.state is RuntimeState.STOPPED


async def test_drain_memaksa_tutup_sesi_yang_macet(
    store, controller_factory, tmp_path: Path
) -> None:
    """Sesi yang tidak pernah selesai harus ditutup, bukan menggantungkan stop."""
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    session = _FakeSession(registry=controller.app.sessions, auto_close=False)  # type: ignore[attr-defined]
    controller.app.sessions[42] = session  # type: ignore[attr-defined]
    await controller.drain_active_calls(timeout=0.05)

    assert session.closed is True
    assert controller.last_drained == 1
    await controller.stop()


async def test_drain_mengabaikan_sesi_yang_gagal_jadwal(
    store, controller_factory, tmp_path: Path
) -> None:
    """Kegagalan satu sesi tidak boleh membatalkan drain sesi lain."""

    class _Broken(_FakeSession):
        def schedule_hangup(self, min_wait: float = 0.0, *, reason: str) -> None:
            raise RuntimeError("sesi rusak")

    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    healthy = _FakeSession(registry=controller.app.sessions)  # type: ignore[attr-defined]
    controller.app.sessions[1] = healthy  # type: ignore[attr-defined]
    broken = _Broken(
        registry=controller.app.sessions, auto_close=False  # type: ignore[attr-defined]
    )
    broken.user_id = 2
    controller.app.sessions[2] = broken  # type: ignore[attr-defined]

    assert await controller.drain_active_calls(timeout=0.05) == 2
    assert healthy.hangup_reasons == ["panel_hangup"]
    await controller.stop()


async def test_drain_tanpa_panggilan_aktif_mengembalikan_nol(
    store, controller_factory, tmp_path: Path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    assert await controller.drain_active_calls() == 0
    assert controller.last_drained == 0
    await controller.stop()


async def test_shutdown_controller(store, controller_factory, tmp_path: Path) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store)
    await controller.start()

    await controller.shutdown()
    assert controller.state is RuntimeState.STOPPED


async def test_runtime_survive_konfigurasi_hilang(store, controller_factory) -> None:
    """Bila kredensial dihapus, refresh tidak boleh melempar."""
    controller = controller_factory(store)
    status = await controller.refresh_settings()
    assert status.state is RuntimeState.STOPPED
    assert status.pending_restart == []