"""Test integrasi `TelegentApp` → `CallObserver` (tiket E1, level orkestrasi).

Memastikan setiap panggilan — termasuk yang **ditolak** — menghasilkan satu
`call_record` dengan `outcome` yang benar, dan event live tetap terbit apa
adanya. Tidak ada jaringan: handler Telegram dipanggil langsung dengan stub.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from telegent.app import TelegentApp
from telegent.config import Settings
from telegent.telegram.call_session import SessionState


class RecordingObserver:
    """Perekam palsu: mencatat urutan hook tanpa menyentuh database."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int, dict]] = []

    def call_incoming(self, tg_call_id: int, user_id: int, *, user_display=None) -> None:
        self.calls.append(
            ("call_incoming", tg_call_id, user_id, {"user_display": user_display})
        )

    def call_started(self, tg_call_id: int, user_id: int) -> None:
        self.calls.append(("call_started", tg_call_id, user_id, {}))

    def call_ended(
        self,
        tg_call_id: int,
        user_id: int,
        *,
        outcome: str,
        end_reason: str | None = None,
        duration_sec: int | None = None,
    ) -> None:
        self.calls.append(
            (
                "call_ended",
                tg_call_id,
                user_id,
                {"outcome": outcome, "end_reason": end_reason, "duration_sec": duration_sec},
            )
        )

    def session_event(self, tg_call_id: int, event: str, data: dict) -> None:
        self.calls.append((f"session:{event}", tg_call_id, 0, data))


def _settings(**overrides) -> Settings:
    base = dict(
        telegram_api_id=1,
        telegram_api_hash="h",
        gemini_api_key="k",
        _env_file=None,  # type: ignore[call-arg]
    )
    base.update(overrides)
    return Settings(**base)


def _dummy_session(call_id: int) -> SimpleNamespace:
    """Sesi palsu: hanya butuh `call_id` agar dianggap "sudah ada"."""
    return SimpleNamespace(call_id=call_id)


#: Skenario penolakan: (nama, setelan, penyiap sebelum handler).
_SCENARIOS: list[tuple[str, dict, str]] = [
    ("rejected_whitelist", {"allowed_user_ids": "7,8"}, ""),
    ("rejected_ratelimit", {"max_calls_per_window": 1}, "ratelimit"),
    ("rejected_duplicate", {"max_calls_per_window": 0}, "duplicate"),
    ("rejected_capacity", {"max_calls_per_window": 0, "max_concurrent_calls": 1}, "capacity"),
]


@pytest.fixture
def no_discard(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Cegah `DiscardCall` sungguhan; kumpulkan user yang ditolak."""
    rejected: list[int] = []

    async def fake_discard(call, reason, user_id):
        rejected.append(user_id)

    monkeypatch.setattr(TelegentApp, "_discard_call", staticmethod(fake_discard))
    return rejected


def _prepare(app: TelegentApp, skenario: str) -> None:
    if skenario == "ratelimit":
        app.rate_limiter.allow(5)  # habiskan kuota pengguna 5
    elif skenario == "duplicate":
        app.sessions[5] = _dummy_session(1)  # type: ignore[assignment]
    elif skenario == "capacity":
        app.sessions[99] = _dummy_session(1)  # type: ignore[assignment]


# ------------------------------------------------------------ penolakan (Q12)


@pytest.mark.parametrize(("outcome", "overrides", "skenario"), _SCENARIOS)
async def test_panggilan_ditolak_masih_membuat_record(
    no_discard: list[int], outcome: str, overrides: dict, skenario: str
) -> None:
    observer = RecordingObserver()
    app = TelegentApp(
        _settings(**overrides), install_signal_handlers=False, call_observer=observer
    )
    _prepare(app, skenario)

    await app._handle_call_requested(SimpleNamespace(id=10, access_hash=99, admin_id=5))

    assert no_discard == [5]
    # Q12: record dibuat saat MASUK, sebelum keputusan penolakan.
    assert [c[0] for c in observer.calls] == ["call_incoming", "call_ended"]
    assert observer.calls[0][1:] == (10, 5, {"user_display": None})
    assert observer.calls[1][3]["outcome"] == outcome
    assert observer.calls[1][3]["end_reason"] == "rejected"


async def test_tanpa_observer_alur_penolakan_tetap_utuh(no_discard: list[int]) -> None:
    """Mode headless (`--no-web`): tidak ada pemantau, perilaku tak berubah."""
    app = TelegentApp(_settings(allowed_user_ids="7,8"), install_signal_handlers=False)

    await app._handle_call_requested(SimpleNamespace(id=10, access_hash=99, admin_id=5))

    assert no_discard == [5]


async def test_event_live_tetap_terbit_untuk_panggilan_ditolak(
    no_discard: list[int],
) -> None:
    """UI tetap melihat penolakan lewat event bus, bukan hanya lewat DB."""
    events: list[tuple[str, dict]] = []
    app = TelegentApp(
        _settings(allowed_user_ids="7,8"),
        install_signal_handlers=False,
        event_sink=lambda name, payload: events.append((name, payload)),
    )

    await app._handle_call_requested(SimpleNamespace(id=10, access_hash=99, admin_id=5))

    assert [name for name, _ in events] == ["call.incoming", "call.ended"]
    assert events[0][1]["tg_call_id"] == 10
    assert events[1][1]["outcome"] == "rejected_whitelist"


# ---------------------------------------------------------------- siklus hidup


async def test_observer_diteruskan_ke_sesi_baru(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sesi yang dibuat memasang `on_event` sehingga transkrip terkirim."""
    observer = RecordingObserver()
    app = TelegentApp(
        _settings(max_calls_per_window=0),
        install_signal_handlers=False,
        call_observer=observer,
    )
    created: list[object] = []

    class FakeSession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.on_hangup = None
            created.append(self)

        def start(self) -> None: ...

        async def close(self) -> None: ...

    async def _invoke(*_args, **_kwargs):
        return SimpleNamespace(g=1, p=2, random=3, g_b=b"x")

    monkeypatch.setattr("telegent.app.CallSession", FakeSession)
    monkeypatch.setattr("telegent.app.NtgAudioSink", lambda ntg, user_id: object())
    monkeypatch.setattr("telegent.app.external_audio_media", lambda *a, **k: object())
    app.app = SimpleNamespace(invoke=_invoke)  # type: ignore[assignment]
    app.ntg = SimpleNamespace(  # type: ignore[assignment]
        create_p2p_call=_invoke,
        init_exchange=_invoke,
        get_protocol=lambda: object(),
    )
    app.signaling = SimpleNamespace()  # type: ignore[assignment]

    await app._handle_call_requested(
        SimpleNamespace(id=10, access_hash=99, admin_id=5, g_a_hash=b"h", protocol=None)
    )

    assert created, "sesi harus dibuat"
    on_event = created[0].kwargs["on_event"]  # type: ignore[attr-defined]
    assert on_event is not None
    on_event("transcript", {"speaker": "ai", "text": "halo"})
    assert observer.calls[-1][0] == "session:transcript"


async def test_call_started_dilaporkan(monkeypatch: pytest.MonkeyPatch) -> None:
    observer = RecordingObserver()
    app = TelegentApp(
        _settings(max_calls_per_window=0),
        install_signal_handlers=False,
        call_observer=observer,
    )

    class FakeSession:
        user_id = 5
        call_id = 10
        state = SessionState.INCOMING_CALL
        signaling_ready = False
        pending_signaling: list = []
        end_reason = None

        def set_state(self, new_state) -> None:
            self.state = new_state

        def start(self) -> None:
            self.state = SessionState.ACTIVE

        async def close(self) -> None: ...

    session = FakeSession()
    app.sessions[5] = session  # type: ignore[assignment]
    app.signaling = SimpleNamespace(flush_pending=lambda _s: None)  # type: ignore[assignment]

    async def _ok(*_args, **_kwargs):
        return None

    app.ntg = SimpleNamespace(  # type: ignore[assignment]
        exchange_keys=_ok,
        connect_p2p=_ok,
        set_stream_sources=_ok,
    )
    monkeypatch.setattr("telegent.app.external_audio_media", lambda *a, **k: object())
    monkeypatch.setattr("telegent.app.to_ntg_rtc_server", lambda conn: conn)

    await app._handle_call_established(
        SimpleNamespace(
            id=10, admin_id=5, participant_id=None, g_a_or_b=b"k", key_fingerprint=b"f",
            connections=[], protocol=None,
        )
    )

    assert ("call_started", 10, 5, {}) in observer.calls


async def test_end_reason_dari_sesi_diteruskan(monkeypatch: pytest.MonkeyPatch) -> None:
    """`end_reason` yang dipilih sesi (mis. `idle`) ikut masuk ke observer."""
    observer = RecordingObserver()
    app = TelegentApp(
        _settings(max_calls_per_window=0),
        install_signal_handlers=False,
        call_observer=observer,
    )

    class FakeSession:
        user_id = 5
        call_id = 10
        duration_seconds = 33
        end_reason = "idle"

        async def close(self) -> None: ...

    session = FakeSession()
    app.sessions[5] = session  # type: ignore[assignment]

    await app._handle_call_discarded(SimpleNamespace(id=10))

    ended = [c for c in observer.calls if c[0] == "call_ended"]
    assert len(ended) == 1
    assert ended[0][3] == {
        "outcome": "answered",
        "end_reason": "idle",
        "duration_sec": 33,
    }


async def test_observer_yang_lempar_tidak_menggagalkan_bot(no_discard: list[int]) -> None:
    """Pemantau rusak tidak boleh menjatuhkan handler panggilan."""

    class Bocah:
        def call_incoming(self, *_a, **_k) -> None:
            raise RuntimeError("monitor mati")

        def call_started(self, *_a, **_k) -> None: ...

        def call_ended(self, *_a, **_k) -> None: ...

        def session_event(self, *_a, **_k) -> None: ...

    app = TelegentApp(
        _settings(allowed_user_ids="7,8"),
        install_signal_handlers=False,
        call_observer=Bocah(),
    )

    await app._handle_call_requested(SimpleNamespace(id=10, access_hash=99, admin_id=5))

    assert no_discard == [5]


async def test_active_sessions_menyalin_daftar_sesi() -> None:
    """`active_sessions()` mengembalikan salinan, bukan objek sesi langsung."""
    app = TelegentApp(_settings(), install_signal_handlers=False)
    assert app.active_sessions() == []

    session = _dummy_session(1)
    app.sessions[5] = session  # type: ignore[assignment]
    sessions = app.active_sessions()
    assert sessions == [session]
    sessions.clear()
    assert len(app.sessions) == 1