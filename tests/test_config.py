"""Unit test konfigurasi."""

from __future__ import annotations

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


def test_allowed_user_ids_parsing():
    settings = _settings(allowed_user_ids="1, 2;3 , ,4")
    assert settings.allowed_user_id_set == {1, 2, 3, 4}


def test_allowed_user_ids_tidak_valid_gagal_saat_load():
    """B2: ID tidak valid harus ditolak saat load, bukan saat panggilan masuk."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _settings(allowed_user_ids="abc,123")


def test_allowed_user_ids_kosong():
    assert _settings().allowed_user_id_set == set()


def test_frame_bytes_default_960():
    assert _settings().tg_frame_bytes == 960


def test_session_workdir_dibuat(tmp_path):
    settings = _settings(session_dir=str(tmp_path / "data"))
    workdir = settings.session_workdir
    assert workdir.exists() and workdir.is_dir()


def test_session_dir_dibaca_dari_env_telegram_session_dir(monkeypatch, tmp_path):
    """Regresi B1: env resmi TELEGRAM_SESSION_DIR harus terbaca (bukan SESSION_DIR)."""
    monkeypatch.setenv("TELEGRAM_SESSION_DIR", str(tmp_path / "data"))
    settings = Settings(
        telegram_api_id=1,
        telegram_api_hash="h",
        gemini_api_key="k",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.session_dir == str(tmp_path / "data")


def test_session_dir_fallback_env_lama(monkeypatch, tmp_path):
    """Env lama SESSION_DIR tetap didukung demi kompatibilitas."""
    monkeypatch.delenv("TELEGRAM_SESSION_DIR", raising=False)
    monkeypatch.setenv("SESSION_DIR", str(tmp_path / "old"))
    settings = Settings(
        telegram_api_id=1,
        telegram_api_hash="h",
        gemini_api_key="k",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.session_dir == str(tmp_path / "old")


def test_default_batas_durasi_dan_rate_limit():
    settings = _settings()
    assert settings.max_call_duration == 600.0
    assert settings.max_calls_per_window == 5
    assert settings.call_window_seconds == 60.0
