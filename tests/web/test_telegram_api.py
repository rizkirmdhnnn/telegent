"""Test API akun & login Telegram (tiket D2).

Pyrogram di-*stub* lewat `monkeypatch.setattr` pada modul `telegram_login`
(menjemput `Client`), sehingga seluruh alur HTTP dapat diuji tanpa jaringan.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from pyrogram.errors import FloodWait, PhoneCodeInvalid, SessionPasswordNeeded
from web_helpers import csrf_of, do_setup

_API_ID = 12345678
_API_HASH = "0123456789abcdef0123456789abcdef"
_PHONE = "+6281234567890"
_CODE = "54321"
_PASSWORD = "rahasia-super-2fa"
_CODE_HASH = "hash-rahasia-yang-panjang"


class FakeClient:
    """Klien Pyrogram palsu yang hanya mendukung operasi login."""

    sign_in_error: BaseException | None = None
    send_code_error: BaseException | None = None
    instances: list["FakeClient"] = []

    def __init__(self, name: str, api_id: int, api_hash: str, workdir: str, **_kwargs: Any) -> None:
        self.name = name
        self.api_id = api_id
        self.api_hash = api_hash
        self.workdir = Path(workdir)
        self.logged_out = False
        # Pyrogram membuat berkas sesi begitu klien dijalankan.
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / f"{name}.session").write_bytes(b"fake-session")
        FakeClient.instances.append(self)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_code(self, phone: str) -> Any:
        if FakeClient.send_code_error is not None:
            raise FakeClient.send_code_error
        return SimpleNamespace(phone_code_hash=_CODE_HASH)

    async def sign_in(self, phone: str, code: str, *, phone_code_hash: str | None = None) -> Any:
        if FakeClient.sign_in_error is not None:
            raise FakeClient.sign_in_error
        return None

    async def check_password(self, password: str) -> Any:
        return None

    async def get_me(self) -> Any:
        return SimpleNamespace(id=42, username="telegent_bot", first_name="Telegent")

    async def log_out(self) -> None:
        self.logged_out = True


@pytest.fixture(autouse=True)
def fake_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Jemput `Client` pada modul layanan agar tidak ada jaringan tersentuh."""
    FakeClient.sign_in_error = None
    FakeClient.send_code_error = None
    FakeClient.instances.clear()
    monkeypatch.setattr("telegent.web.telegram_login.Client", FakeClient)
    yield
    FakeClient.instances.clear()


@pytest.fixture
def client_with_telegram(live_client: TestClient) -> TestClient:
    """Admin yang sudah setup + kredensial Telegram terisi."""
    do_setup(live_client)
    resp = live_client.put(
        "/api/credentials/telegram",
        json={"api_id": _API_ID, "api_hash": _API_HASH},
        headers={"X-CSRF-Token": csrf_of(live_client)},
    )
    assert resp.status_code == 200
    return live_client


def _headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_of(client)}


def _start(client: TestClient, phone: str = _PHONE) -> dict[str, Any]:
    resp = client.post(
        "/api/telegram/login/start", json={"phone": phone}, headers=_headers(client)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _login(client: TestClient) -> dict[str, Any]:
    """Login penuh lewat HTTP dan kembalikan baris status terakhir."""
    start = _start(client)
    resp = client.post(
        "/api/telegram/login/verify",
        json={"flow_id": start["flow_id"], "code": _CODE},
        headers=_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return client.get("/api/telegram/status").json()


# ------------------------------------------------------------------- endpoint


def test_status_membutuhkan_admin(client: TestClient) -> None:
    assert client.get("/api/telegram/status").status_code == 401


def test_status_tidak_butuh_csrf(client_with_telegram: TestClient) -> None:
    resp = client_with_telegram.get("/api/telegram/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "logged_out"
    assert body["credentials_configured"] is True
    assert body["user"] is None


def test_mutasi_membutuhkan_csrf(client_with_telegram: TestClient) -> None:
    for path, payload in (
        ("/api/telegram/login/start", {"phone": _PHONE}),
        ("/api/telegram/login/verify", {"flow_id": 1, "code": _CODE}),
        ("/api/telegram/login/password", {"flow_id": 1, "password": _PASSWORD}),
        ("/api/telegram/login/cancel", {"flow_id": 1}),
        ("/api/telegram/logout", None),
    ):
        resp = client_with_telegram.post(path, json=payload)
        assert resp.status_code == 403, f"{path} lolos tanpa CSRF"
        assert resp.json()["error"]["code"] == "csrf_failed"


def test_alur_login_penuh_lewat_http(client_with_telegram: TestClient) -> None:
    status = _login(client_with_telegram)

    assert status["status"] == "logged_in"
    assert status["user"] == {"id": 42, "username": "telegent_bot", "first_name": "Telegent"}
    assert status["phone"] == _PHONE
    assert status["last_error"] is None
    assert isinstance(status["logged_in_at"], str)
    assert status["session_mismatch"] is False


def test_alur_login_dengan_2fa(client_with_telegram: TestClient) -> None:
    FakeClient.sign_in_error = SessionPasswordNeeded()
    start = _start(client_with_telegram)

    resp = client_with_telegram.post(
        "/api/telegram/login/verify",
        json={"flow_id": start["flow_id"], "code": _CODE},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": "password"}

    resp = client_with_telegram.post(
        "/api/telegram/login/password",
        json={"flow_id": start["flow_id"], "password": _PASSWORD},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert client_with_telegram.get("/api/telegram/status").json()["status"] == "logged_in"


def test_logout_mengosongkan_status(client_with_telegram: TestClient) -> None:
    _login(client_with_telegram)

    resp = client_with_telegram.post("/api/telegram/logout", headers=_headers(client_with_telegram))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    status = client_with_telegram.get("/api/telegram/status").json()
    assert status["status"] == "logged_out"
    assert status["user"] is None
    assert FakeClient.instances[-1].logged_out is True


def test_cancel_mengosongkan_alur(client_with_telegram: TestClient) -> None:
    start = _start(client_with_telegram)
    resp = client_with_telegram.post(
        "/api/telegram/login/cancel",
        json={"flow_id": start["flow_id"]},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 200

    resp = client_with_telegram.post(
        "/api/telegram/login/cancel",
        json={"flow_id": start["flow_id"]},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "flow_not_found"


def test_login_kedua_ditolak_sampai_logout(client_with_telegram: TestClient) -> None:
    _login(client_with_telegram)

    resp = client_with_telegram.post(
        "/api/telegram/login/start",
        json={"phone": "+6289999999999"},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "already_logged_in"


def test_mulai_ulang_membatalkan_flow_sebelumnya(client_with_telegram: TestClient) -> None:
    pertama = _start(client_with_telegram)
    kedua = _start(client_with_telegram)

    resp = client_with_telegram.post(
        "/api/telegram/login/verify",
        json={"flow_id": pertama["flow_id"], "code": _CODE},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code in (404, 410)
    assert resp.json()["error"]["code"] in {"flow_not_found", "flow_expired"}
    assert kedua["next"] == "code"


# ------------------------------------------------------------------ error path


def test_tanpa_kredensial_menghasilkan_kode_bukan_500(live_client: TestClient) -> None:
    do_setup(live_client)
    resp = live_client.post(
        "/api/telegram/login/start", json={"phone": _PHONE}, headers=_headers(live_client)
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "api_credentials_missing"


def test_flood_wait_mengembalikan_retry_after(client_with_telegram: TestClient) -> None:
    FakeClient.send_code_error = FloodWait(value=95)
    resp = client_with_telegram.post(
        "/api/telegram/login/start",
        json={"phone": _PHONE},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 429
    error = resp.json()["error"]
    assert error["code"] == "flood_wait"
    assert error["fields"]["retry_after"] == 95


def test_kode_salah_mengembalikan_kode_stabil(client_with_telegram: TestClient) -> None:
    start = _start(client_with_telegram)
    FakeClient.sign_in_error = PhoneCodeInvalid()
    resp = client_with_telegram.post(
        "/api/telegram/login/verify",
        json={"flow_id": start["flow_id"], "code": "000000"},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "code_invalid"


def test_nomor_tidak_valid_ditolak_backend(client_with_telegram: TestClient) -> None:
    resp = client_with_telegram.post(
        "/api/telegram/login/start",
        json={"phone": "bukan-nomor"},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "phone_invalid"
    assert FakeClient.instances == []


def test_body_tidak_valid_ditolak_422(client_with_telegram: TestClient) -> None:
    resp = client_with_telegram.post(
        "/api/telegram/login/verify",
        json={"flow_id": 0, "code": ""},
        headers=_headers(client_with_telegram),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_login_ditolak_saat_bot_jalan(client_with_telegram: TestClient) -> None:
    from telegent.web.runtime import RuntimeState

    runtime = client_with_telegram.app.state.runtime
    runtime._state = RuntimeState.RUNNING  # type: ignore[attr-defined]

    for path, payload in (
        ("/api/telegram/login/start", {"phone": _PHONE}),
        ("/api/telegram/logout", None),
    ):
        resp = client_with_telegram.post(path, json=payload, headers=_headers(client_with_telegram))
        assert resp.status_code == 409, path
        assert resp.json()["error"]["code"] == "bot_running", path

    # Status tetap bisa dibaca (hanya-baca) saat bot berjalan.
    assert client_with_telegram.get("/api/telegram/status").status_code == 200


# --------------------------------------------------------------------- audit


def _audit(client: TestClient, action: str) -> list[dict[str, Any]]:
    resp = client.get("/api/audit", params={"action": action, "page_size": 50})
    assert resp.status_code == 200
    return list(reversed(resp.json()["items"]))  # terlama dulu


def test_setiap_langkah_login_tercatat_di_audit(client_with_telegram: TestClient) -> None:
    _login(client_with_telegram)
    client_with_telegram.post("/api/telegram/logout", headers=_headers(client_with_telegram))

    langkah = [item["after"]["step"] for item in _audit(client_with_telegram, "telegram.login")]
    assert langkah == ["start", "verify"]
    logout = _audit(client_with_telegram, "telegram.logout")
    assert len(logout) == 1
    assert logout[0]["after"]["status"] == "logged_out"


def test_audit_tidak_menyimpan_secret(client_with_telegram: TestClient) -> None:
    FakeClient.sign_in_error = SessionPasswordNeeded()
    start = _start(client_with_telegram)
    client_with_telegram.post(
        "/api/telegram/login/verify",
        json={"flow_id": start["flow_id"], "code": _CODE},
        headers=_headers(client_with_telegram),
    )
    client_with_telegram.post(
        "/api/telegram/login/password",
        json={"flow_id": start["flow_id"], "password": _PASSWORD},
        headers=_headers(client_with_telegram),
    )

    isi = [item["before"] for item in _audit(client_with_telegram, "telegram.login")]
    isi += [item["after"] for item in _audit(client_with_telegram, "telegram.login")]
    isi += [item["before"] for item in _audit(client_with_telegram, "telegram.logout")]
    isi += [item["after"] for item in _audit(client_with_telegram, "telegram.logout")]
    teks = repr(isi)

    assert _PHONE not in teks
    assert _CODE not in teks
    assert _PASSWORD not in teks
    assert _CODE_HASH not in teks
    assert _API_HASH not in teks


def test_gagal_login_juga_tercatat_di_audit(client_with_telegram: TestClient) -> None:
    start = _start(client_with_telegram)
    FakeClient.sign_in_error = PhoneCodeInvalid()
    client_with_telegram.post(
        "/api/telegram/login/verify",
        json={"flow_id": start["flow_id"], "code": "000000"},
        headers=_headers(client_with_telegram),
    )

    items = _audit(client_with_telegram, "telegram.login")
    assert items[-1]["after"] == {
        "step": "verify",
        "flow_id": start["flow_id"],
        "error": "code_invalid",
    }