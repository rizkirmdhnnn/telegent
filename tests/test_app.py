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
