"""Fixture bersama untuk pengujian Telegent."""

from __future__ import annotations

import pytest

from telegent.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        telegram_api_id=1,
        telegram_api_hash="hash",
        gemini_api_key="key",
        telegram_session_name="test_session",
        _env_file=None,  # type: ignore[call-arg]
    )
