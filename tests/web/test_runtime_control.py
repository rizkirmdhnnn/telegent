"""Test endpoint kontrol runtime: start/stop/restart (tiket F1).

Runtime memakai `_FakeTelegent` sehingga tidak ada jaringan yang tersentuh.
Sesi Telegram palsu dibuat di direktori data agar controller menganggap akun
sudah login.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from web_helpers import csrf_of, do_setup

from telegent.config import Settings
from telegent.web.runtime import RuntimeController

_CREDENTIALS = {
    "telegram_api_id": 12345678,
    "telegram_api_hash": "0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaSy0123456789012345678901234567890",
}

_SESSION_NAME = "userbot_session"


class _FakeSession:
    """Sesi panggilan palsu: mencatat hangup graceful & penutupan paksa."""

    def __init__(self, user_id: int, *, auto_close: bool = True) -> None:
        self.user_id = user_id
        self.auto_close = auto_close
        self.hangup_reasons: list[str] = []
        self.closed = False

    def schedule_hangup(self, min_wait: float = 0.0, *, reason: str) -> None:
        self.hangup_reasons.append(reason)


class _FakeTelegent:
    """Pengganti `TelegentApp` yang mengelola sesi lewat dict sederhana."""

    created: list["_FakeTelegent"] = []
    fail_start = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.stop_event = __import__("asyncio").Event()
        self.sessions: dict[int, _FakeSession] = {}
        _FakeTelegent.created.append(self)

    def active_sessions(self) -> list[_FakeSession]:
        return list(self.sessions.values())

    async def start(self) -> None:
        if _FakeTelegent.fail_start:
            raise RuntimeError("kredensial ditolak")

    async def stop(self) -> None:
        self.stop_event.set()

    async def wait_stopped(self) -> None:
        await self.stop_event.wait()

    async def shutdown(self) -> None:
        self.sessions.clear()

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings

    def status_payload(self) -> dict[str, Any]:
        return {
            "running": True,
            "active_calls": len(self.sessions),
            "model": self.settings.gemini_model,
            "logged_in_user": {"id": 99, "first_name": "Bot", "username": "bot"},
        }


@pytest.fixture(autouse=True)
def fake_runtime() -> Iterator[None]:
    _FakeTelegent.created.clear()
    _FakeTelegent.fail_start = False
    yield
    _FakeTelegent.created.clear()


@pytest.fixture
def control_client(live_client: TestClient) -> TestClient:
    """Admin siap + runtime memakai fake, sesi Telegram tersedia di disk."""
    controller = live_client.app.state.runtime
    controller._app_factory = lambda settings: _FakeTelegent(settings)  # type: ignore[assignment]
    cfg = live_client.app.state.bootstrap
    cfg.ensure_data_dir()
    (cfg.data_dir / f"{_SESSION_NAME}.session").write_bytes(b"fake")
    do_setup(live_client)
    return live_client


def _headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_of(client)}


def _configure(client: TestClient) -> None:
    resp = client.put(
        "/api/credentials/gemini",
        json={"api_key": _CREDENTIALS["gemini_api_key"]},
        headers=_headers(client),
    )
    assert resp.status_code == 200, resp.text
    resp = client.put(
        "/api/credentials/telegram",
        json={
            "api_id": _CREDENTIALS["telegram_api_id"],
            "api_hash": _CREDENTIALS["telegram_api_hash"],
        },
        headers=_headers(client),
    )
    assert resp.status_code == 200, resp.text


def _add_session(runtime: RuntimeController, user_id: int) -> _FakeSession:
    """Sisipkan sesi aktif pada aplikasi yang sedang berjalan."""
    assert runtime.app is not None
    session = _FakeSession(user_id)
    runtime.app.sessions[user_id] = session  # type: ignore[attr-defined]
    return session


# ------------------------------------------------------------------- guardrail


@pytest.mark.parametrize("path", ["/api/runtime/start", "/api/runtime/stop", "/api/runtime/restart"])
def test_mutasi_menolak_tanpa_sesi(live_client: TestClient, path: str) -> None:
    assert live_client.post(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/runtime/start", "/api/runtime/stop", "/api/runtime/restart"])
def test_mutasi_menolak_tanpa_csrf(control_client: TestClient, path: str) -> None:
    assert control_client.post(path).status_code == 403


# ---------------------------------------------------------------------- start


def test_start_tanpa_kredensial_mengembalikan_not_configured(control_client: TestClient) -> None:
    resp = control_client.post("/api/runtime/start", headers=_headers(control_client))

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "not_configured"
    assert body["running"] is False


def test_start_tanpa_login_telegram_mengembalikan_needs_login(control_client: TestClient) -> None:
    _configure(control_client)
    (control_client.app.state.bootstrap.data_dir / f"{_SESSION_NAME}.session").unlink()

    resp = control_client.post("/api/runtime/start", headers=_headers(control_client))

    assert resp.status_code == 200
    assert resp.json()["state"] == "needs_login"


def test_start_berhasil_mengembalikan_status_runtime(control_client: TestClient) -> None:
    _configure(control_client)

    body = control_client.post("/api/runtime/start", headers=_headers(control_client)).json()

    assert body["state"] == "running"
    assert body["running"] is True
    assert body["since"]
    assert len(_FakeTelegent.created) == 1


def test_start_gagal_menjadi_error_tanpa_500(control_client: TestClient) -> None:
    _configure(control_client)
    _FakeTelegent.fail_start = True

    resp = control_client.post("/api/runtime/start", headers=_headers(control_client))

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "error"
    assert body["last_error"]
    assert body["running"] is False


def test_start_klik_ganda_tidak_menggandakan_instance(control_client: TestClient) -> None:
    _configure(control_client)
    headers = _headers(control_client)

    control_client.post("/api/runtime/start", headers=headers)
    control_client.post("/api/runtime/start", headers=headers)

    assert len(_FakeTelegent.created) == 1
    assert control_client.get("/api/runtime/status").json()["running"] is True
    control_client.post("/api/runtime/stop", headers=headers)


# ----------------------------------------------------------------------- stop


def test_stop_menghentikan_bot(control_client: TestClient) -> None:
    _configure(control_client)
    headers = _headers(control_client)
    control_client.post("/api/runtime/start", headers=headers)

    body = control_client.post("/api/runtime/stop", headers=headers).json()

    assert body["state"] == "stopped"
    assert body["running"] is False
    assert control_client.get("/api/runtime/status").json()["running"] is False


def test_stop_klik_ganda_aman(control_client: TestClient) -> None:
    _configure(control_client)
    headers = _headers(control_client)
    control_client.post("/api/runtime/start", headers=headers)

    control_client.post("/api/runtime/stop", headers=headers)
    second = control_client.post("/api/runtime/stop", headers=headers)

    assert second.status_code == 200
    assert second.json()["state"] == "stopped"


def test_stop_mengakhiri_panggilan_aktif_secara_graceful(control_client: TestClient) -> None:
    """Keputusan F1: panggilan aktif di-*drain*, bukan langsung diputus."""
    _configure(control_client)
    headers = _headers(control_client)
    control_client.post("/api/runtime/start", headers=headers)
    runtime: RuntimeController = control_client.app.state.runtime
    session = _add_session(runtime, 5550001)

    body = control_client.post("/api/runtime/stop", headers=headers).json()

    assert body["state"] == "stopped"
    assert session.hangup_reasons == ["panel_hangup"]
    assert session.closed is False  # ditutup oleh app.shutdown(), bukan langsung


def test_restart_mengakhiri_panggilan_aktif(control_client: TestClient) -> None:
    _configure(control_client)
    headers = _headers(control_client)
    control_client.post("/api/runtime/start", headers=headers)
    runtime: RuntimeController = control_client.app.state.runtime
    session = _add_session(runtime, 5550002)

    body = control_client.post("/api/runtime/restart", headers=headers).json()

    assert body["state"] == "running"
    assert session.hangup_reasons == ["panel_hangup"]
    assert len(_FakeTelegent.created) == 2
    control_client.post("/api/runtime/stop", headers=headers)


def test_restart_menggunakan_konfigurasi_terbaru(control_client: TestClient) -> None:
    _configure(control_client)
    headers = _headers(control_client)
    control_client.post("/api/runtime/start", headers=headers)
    control_client.put(
        "/api/settings",
        json={"changes": {"max_concurrent_calls": 7}},
        headers=headers,
    )

    control_client.post("/api/runtime/restart", headers=headers)

    assert _FakeTelegent.created[-1].settings.max_concurrent_calls == 7
    control_client.post("/api/runtime/stop", headers=headers)


# ---------------------------------------------------------------------- audit


@pytest.mark.parametrize(
    ("action", "method"),
    [
        ("runtime.start", "start"),
        ("runtime.stop", "stop"),
        ("runtime.restart", "restart"),
        ("runtime.apply", "apply"),
    ],
)
def test_aksi_berhasil_tercatat_di_audit(
    control_client: TestClient, action: str, method: str
) -> None:
    _configure(control_client)
    headers = _headers(control_client)
    control_client.post("/api/runtime/start", headers=headers)
    control_client.post("/api/runtime/stop", headers=headers)
    before = control_client.get(
        "/api/audit", params={"action": action, "page_size": 1}
    ).json()["total"]

    control_client.post(f"/api/runtime/{method}", headers=headers)

    audit = control_client.get("/api/audit", params={"action": action}).json()
    # Tiap aksi menambah tepat satu entri (klik ganda tidak boleh menggandakan).
    assert audit["total"] == before + 1
    item = audit["items"][0]
    assert item["actor"] == "admin"
    assert item["target"] == "runtime"
    assert item["after"]["state"]
    assert item["before"] is not None
    control_client.post("/api/runtime/stop", headers=headers)


def test_start_gagal_tercatat_di_audit(control_client: TestClient) -> None:
    _configure(control_client)
    _FakeTelegent.fail_start = True

    control_client.post("/api/runtime/start", headers=_headers(control_client))

    audit = control_client.get("/api/audit", params={"action": "runtime.start"}).json()
    assert audit["total"] == 1
    assert audit["items"][0]["actor"] == "admin"
    assert audit["items"][0]["target"] == "runtime"
    assert audit["items"][0]["after"]["state"] == "error"


def test_audit_tidak_membocorkan_secret(control_client: TestClient) -> None:
    _configure(control_client)
    _FakeTelegent.fail_start = True

    control_client.post("/api/runtime/start", headers=_headers(control_client))

    audit = control_client.get("/api/audit", params={"action": "runtime.start"}).json()
    assert _CREDENTIALS["gemini_api_key"] not in str(audit)
    assert _CREDENTIALS["telegram_api_hash"] not in str(audit)