"""Test hidrasi konfigurasi tool ke runtime (perbaikan C3 langkah 4)."""

from __future__ import annotations

from typing import Any

import pytest

from telegent.ai.tools.builtin import DEFAULT_TIMEZONE, make_datetime_tool
from telegent.ai.tools.registry import ToolRegistry
from telegent.config import Settings
from telegent.web.runtime import RuntimeController, RuntimeState
from telegent.web.tools_store import load_tool_settings, save_tool_setting

_CREDENTIALS = {
    "telegram_api_id": 12345678,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}


class _FakeTelegent:
    created: list["_FakeTelegent"] = []

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tools = ToolRegistry()
        self.stop_event = __import__("asyncio").Event()
        self.sessions: dict[int, Any] = {}
        _FakeTelegent.created.append(self)

    def active_sessions(self) -> list[Any]:
        return list(self.sessions.values())

    async def start(self) -> None: ...

    async def stop(self) -> None:
        self.stop_event.set()

    async def wait_stopped(self) -> None:
        await self.stop_event.wait()

    async def shutdown(self) -> None: ...

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings

    def apply_tool_config(self, name: str, **kwargs: Any) -> None:
        self.tools.configure(name, **kwargs)

    def status_payload(self) -> dict:
        return {"running": True, "active_calls": 0, "model": self.settings.gemini_model,
                "logged_in_user": None}


@pytest.fixture
def controller_factory(tmp_path):
    _FakeTelegent.created.clear()

    def make(store, db):
        return RuntimeController(
            store,
            app_factory=lambda settings: _FakeTelegent(settings),  # type: ignore[arg-type,return-value]
            session_dir=tmp_path / "sessions",
            tool_config_provider=lambda: _configs(db),
        )

    return make


async def _configs(db) -> dict[str, dict]:
    from telegent.web.tools_store import tool_configs_for_runtime

    return await tool_configs_for_runtime(db)


def _make_session(tmp_path) -> None:
    directory = tmp_path / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "userbot_session.session").write_bytes(b"fake")


# ------------------------------------------------------------- tools_store


async def test_simpan_dan_baca_konfigurasi_tool(database) -> None:
    before, after = await save_tool_setting(
        database, "get_current_datetime", config={"default_timezone": "Asia/Makassar"}
    )
    assert before.enabled is True and before.config is None
    assert after.config == {"default_timezone": "Asia/Makassar"}

    settings = await load_tool_settings(database)
    assert settings["get_current_datetime"].enabled is True
    assert settings["get_current_datetime"].config == {"default_timezone": "Asia/Makassar"}


async def test_simpan_hanya_enabled(database) -> None:
    await save_tool_setting(database, "get_current_datetime", enabled=False)
    settings = await load_tool_settings(database)
    assert settings["get_current_datetime"].enabled is False


async def test_konfigurasi_tidak_ikut_ditimpa(database) -> None:
    await save_tool_setting(database, "get_current_datetime", config={"default_timezone": "UTC"})
    _, after = await save_tool_setting(database, "get_current_datetime", enabled=True)
    assert after.config == {"default_timezone": "UTC"}


# ------------------------------------------------- registry tanpa hardcode


def test_registry_menerapkan_konfigurasi_melalui_config_factory() -> None:
    registry = ToolRegistry().register(make_datetime_tool())
    registry.apply_configs({"get_current_datetime": {"default_timezone": "Asia/Makassar"}})

    spec = registry.specs["get_current_datetime"]
    # Zona waktu default tersampaikan ke handler melalui spec yang dibangun ulang.
    assert spec.config_factory is not None
    assert spec.config_factory({}).parameters_json_schema["properties"]["timezone"]


def test_apply_configs_menabaikan_tool_tidak_dikenal() -> None:
    registry = ToolRegistry().register(make_datetime_tool())
    registry.apply_configs({"tidak_ada": {"x": 1}})  # tidak boleh melempar


def test_apply_configs_menangani_config_rusak() -> None:
    registry = ToolRegistry().register(make_datetime_tool())
    registry.apply_configs({"get_current_datetime": {"default_timezone": None}})
    assert registry.specs["get_current_datetime"].name == "get_current_datetime"


def test_zona_waktu_bawaan_tetap_konsisten() -> None:
    assert DEFAULT_TIMEZONE == "Asia/Jakarta"


# --------------------------------------------------------- hidrasi runtime


async def test_konfigurasi_tool_didpatkan_setiap_start(
    store, database, controller_factory, tmp_path
) -> None:
    await store.update(_CREDENTIALS)
    await save_tool_setting(
        database, "get_current_datetime", config={"default_timezone": "Asia/Makassar"}
    )
    _make_session(tmp_path)

    controller = controller_factory(store, database)
    await controller.start()

    assert controller.state is RuntimeState.RUNNING
    # Konfigurasi dihidrasi SETIAP start (bukan hanya saat runtime dibangun).
    assert controller.tool_configs == {
        "get_current_datetime": {"default_timezone": "Asia/Makassar"}
    }
    await controller.stop()


async def test_konfigurasi_tersimpan_saat_bot_mati(
    store, database, controller_factory, tmp_path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store, database)

    # Bot mati: perubahan tetap tersimpan untuk start berikutnya.
    await controller.apply_tool_config(
        "get_current_datetime", config={"default_timezone": "Asia/Makassar"}
    )
    await controller.start()

    assert controller.tool_configs == {
        "get_current_datetime": {"default_timezone": "Asia/Makassar"}
    }
    await controller.stop()


async def test_perubahan_tool_diterapkan_ke_bot_yang_hidup(
    store, database, controller_factory, tmp_path
) -> None:
    await store.update(_CREDENTIALS)
    _make_session(tmp_path)
    controller = controller_factory(store, database)
    await controller.start()

    await controller.apply_tool_config(
        "get_current_datetime", enabled=False, config={"default_timezone": "UTC"}
    )

    registry = _FakeTelegent.created[0].tools
    assert registry.is_enabled("get_current_datetime") is False
    await controller.stop()