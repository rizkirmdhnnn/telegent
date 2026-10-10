"""Unit test orkestrasi aplikasi (tanpa jaringan)."""

from __future__ import annotations

from types import SimpleNamespace

from telegent.app import TelegentApp
from telegent.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        telegram_api_id=1,
        telegram_api_hash="h",
        gemini_api_key="k",
        _env_file=None,  # type: ignore[call-arg]
    )
    base.update(overrides)
    return Settings(**base)


async def test_rate_limit_menolak_panggilan_beruntun(monkeypatch):
    settings = _settings(max_calls_per_window=1, call_window_seconds=60)
    app = TelegentApp(settings)

    denied: list[int] = []

    async def fake_discard(call, reason, user_id):
        denied.append(user_id)

    monkeypatch.setattr(app, "_discard_call", fake_discard)
    call = SimpleNamespace(id=10, access_hash=99, admin_id=5)

    # Percobaan pertama menghabiskan kuota rate-limit pengguna 5.
    assert app.rate_limiter.allow(5) is True

    await app._handle_call_requested(call)

    assert denied == [5]


async def test_whitelist_menolak_user_luar_daftar(monkeypatch):
    settings = _settings(allowed_user_ids="7,8", max_calls_per_window=0)
    app = TelegentApp(settings)

    denied: list[int] = []

    async def fake_discard(call, reason, user_id):
        denied.append(user_id)

    monkeypatch.setattr(app, "_discard_call", fake_discard)
    call = SimpleNamespace(id=10, access_hash=99, admin_id=999)

    await app._handle_call_requested(call)

    assert denied == [999]


async def test_tolak_panggilan_ganda_user_yang_sama(monkeypatch):
    """B4: user yang sudah punya sesi tidak boleh membuat sesi baru (anti-leak)."""
    settings = _settings(max_calls_per_window=0)
    app = TelegentApp(settings)
    app.sessions[5] = SimpleNamespace(call_id=1)

    denied: list[int] = []

    async def fake_discard(call, reason, user_id):
        denied.append(user_id)

    monkeypatch.setattr(app, "_discard_call", fake_discard)
    call = SimpleNamespace(id=10, access_hash=99, admin_id=5)

    await app._handle_call_requested(call)

    assert denied == [5]
    # Sesi lama tetap utuh (tidak tertimpa).
    assert app.sessions[5].call_id == 1


async def test_phone_call_diabaikan_bila_sesi_tidak_incoming(monkeypatch):
    """B4: update PhoneCall terduplikasi tidak menyiapkan media dua kali."""
    from telegent.telegram.call_session import SessionState

    settings = _settings()
    app = TelegentApp(settings)
    session = SimpleNamespace(user_id=5, call_id=10, state=SessionState.ACTIVE)
    app.sessions[5] = session

    call = SimpleNamespace(id=10, admin_id=5, participant_id=None)

    # Tidak boleh menyentuh ntg (state bukan INCOMING_CALL) -> cukup tidak error.
    await app._handle_call_established(call)


def test_on_signaling_data_menahan_lalu_mengirim(monkeypatch):
    """B3: buffering signaling dijalankan di loop (helper tersendiri)."""
    settings = _settings()
    app = TelegentApp(settings)

    dispatched: list[bytes] = []

    class FakeSignaling:
        def dispatch(self, session, data):
            dispatched.append(data)

    app.signaling = FakeSignaling()  # type: ignore[assignment]
    session = SimpleNamespace(signaling_ready=False, pending_signaling=[])
    app.sessions[5] = session  # type: ignore[assignment]

    app._on_signaling_data(5, b"early")
    assert session.pending_signaling == [b"early"]
    assert dispatched == []

    session.signaling_ready = True
    app._on_signaling_data(5, b"late")
    assert dispatched == [b"late"]


async def test_deliver_incoming_pcm_diteruskan_ke_sesi():
    settings = _settings()
    app = TelegentApp(settings)

    received: list[bytes] = []
    session = SimpleNamespace(handle_incoming_telegram_pcm=received.append)
    app.sessions[5] = session  # type: ignore[assignment]

    app._deliver_incoming_pcm(5, b"pcm")
    assert received == [b"pcm"]


async def test_signaling_dispatch_dari_loop_mengirim():
    """B3: dispatch aman dipanggil dari dalam event loop (pakai create_task)."""
    import asyncio

    from telegent.telegram.signaling import SignalingService

    sent: list[bytes] = []

    class FakeApp:
        async def invoke(self, query):
            sent.append(query.data)
            return None

    svc = SignalingService(FakeApp(), asyncio.get_running_loop(), None)
    session = SimpleNamespace(call_id=1, access_hash=1)

    svc.dispatch(session, b"ice")
    await asyncio.sleep(0)

    assert sent == [b"ice"]
