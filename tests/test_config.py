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


def test_allowed_user_ids_kosong():
    assert _settings().allowed_user_id_set == set()


def test_frame_bytes_default_960():
    assert _settings().tg_frame_bytes == 960


def test_session_workdir_dibuat(tmp_path):
    settings = _settings(session_dir=str(tmp_path / "data"))
    workdir = settings.session_workdir
    assert workdir.exists() and workdir.is_dir()
