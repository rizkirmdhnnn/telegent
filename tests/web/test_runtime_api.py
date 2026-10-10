"""Test endpoint status runtime & penerapan perubahan tertunda (Fase 1)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from web_helpers import csrf_of, do_setup

from telegent.config import Settings
from telegent.web.runtime import RuntimeState

_CREDENTIALS = {
    "telegram_api_id": 12345678,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}


class _FakeTelegent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stop_event = __import__("asyncio").Event()

    async def start(self) -> None: ...

    async def stop(self) -> None:
        self.stop_event.set()

    async def wait_stopped(self) -> None:
        await self.stop_event.wait()

    async def shutdown(self) -> None: ...

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings

    def status_payload(self) -> dict[str, Any]:
        return {
            "running": True,
            "active_calls": 0,
            "model": self.settings.gemini_model,
            "logged_in_user": None,
        }


@pytest.fixture
def live_runtime(live_client: TestClient):
    """Ganti app factory runtime dengan fake agar tanpa jaringan."""
    controller = live_client.app.state.runtime
    controller._app_factory = lambda settings: _FakeTelegent(settings)  # type: ignore[assignment]
    return controller


# ------------------------------------------------------------------- status


def test_status_menolak_tanpa_sesi(live_client: TestClient) -> None:
    assert live_client.get("/api/runtime/status").status_code == 401


def test_status_setelah_login(live_client: TestClient) -> None:
    do_setup(live_client)
    body = live_client.get("/api/runtime/status").json()

    assert body["state"] == RuntimeState.STOPPED.value
    assert body["running"] is False
    assert body["active_calls"] == 0
    assert body["pending_restart"] == []


def test_status_menampilkan_pending_restart(live_client: TestClient) -> None:
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}
    live_client.put(
        "/api/settings",
        json={"changes": {"gemini_api_key": "AIzaBerubah012345678901234567890"}},
        headers=headers,
    )

    body = live_client.get("/api/runtime/status").json()
    assert body["pending_restart"] == ["gemini_api_key"]


# -------------------------------------------------------------------- apply


def test_apply_menolak_tanpa_sesi(live_client: TestClient) -> None:
    assert live_client.post("/api/runtime/apply").status_code == 401


def test_apply_menolak_tanpa_csrf(live_client: TestClient) -> None:
    do_setup(live_client)
    assert live_client.post("/api/runtime/apply").status_code == 403


def test_apply_tanpa_perubahan_hanya_menyegarkan(live_client: TestClient, live_runtime) -> None:
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}

    resp = live_client.post("/api/runtime/apply", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["state"] == "stopped"

    # Tidak ada restart: state tetap stopped dan tak ada audit apply.
    audit = live_client.get("/api/audit").json()
    assert all(item["action"] != "runtime.apply" for item in audit["items"])


def test_apply_mencatat_audit_saat_ada_perubahan(live_client: TestClient, live_runtime) -> None:
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}

    live_client.put(
        "/api/settings",
        json={"changes": {"gemini_api_key": "AIzaBerubah012345678901234567890"}},
        headers=headers,
    )

    assert live_client.get("/api/runtime/status").json()["pending_restart"] == ["gemini_api_key"]

    resp = live_client.post("/api/runtime/apply", headers=headers)
    assert resp.status_code == 200

    audit = live_client.get("/api/audit", params={"action": "runtime.apply"}).json()
    assert audit["total"] == 1
    assert audit["items"][0]["actor"] == "admin"