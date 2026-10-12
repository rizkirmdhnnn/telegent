"""Test handler galat, dependency 503, dan `healthz` (tiket H1).

Tiga hal yang dijaga di sini:

- seluruh galat API berbentuk `{"error": {code, message?, fields?}}` sehingga
  frontend bisa menerjemahkan berdasarkan `code` (aturan #2);
- dependency mengembalikan 503 yang **jelas**, bukan `AttributeError` saat
  lifespan belum selesai atau sudah ditutup;
- `healthz` tetap jujur soal kondisi DB dan.mode fake.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from telegent.web.db.base import Database
from telegent.web.deps import (
    get_call_recorder,
    get_cipher,
    get_database,
    get_runtime,
    get_settings_store,
    get_telegram_login,
)
from telegent.web.errors import APIError


# ---------------------------------------------------------------- healthz


def test_healthz_mencerminkan_mode_fake_normal(
    live_client: TestClient, app: FastAPI
) -> None:
    app.state.fake = False
    assert live_client.get("/api/healthz").json()["fake"] is False


def test_healthz_mencerminkan_mode_fake_aktif(
    live_client: TestClient, app: FastAPI
) -> None:
    app.state.fake = True
    assert live_client.get("/api/healthz").json()["fake"] is True


def test_healthz_sebelum_lifespan(client: TestClient) -> None:
    """Sebelum lifespan, DB belum ada — jawaban harus jujur, bukan error."""
    body = client.get("/api/healthz").json()
    assert body["db"] == "not_started"
    assert body["ok"] is True


def test_healthz_db_tidak_tersedia(live_client: TestClient, app: FastAPI) -> None:
    async def _ping() -> bool:
        return False

    db = app.state.db
    assert isinstance(db, Database)
    db.ping = _ping  # type: ignore[method-assign]
    assert live_client.get("/api/healthz").json()["db"] == "unavailable"


# ------------------------------------------------------------- dependency 503


def _request(app: FastAPI) -> Request:
    """Request kosong untuk memanggil dependency secara langsung."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/healthz",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
    )


@pytest.mark.parametrize(
    ("getter", "expected_code"),
    [
        (get_database, "database_unavailable"),
        (get_settings_store, "store_unavailable"),
        (get_cipher, "store_unavailable"),
        (get_runtime, "runtime_unavailable"),
        (get_call_recorder, "runtime_unavailable"),
        (get_telegram_login, "telegram_unavailable"),
    ],
)
def test_dependency_melempar_503_jika_belum_siap(
    app: FastAPI, getter: Any, expected_code: str
) -> None:
    """Semua state sengaja `None` (app dibuat tanpa lifespan)."""
    app.state.db = None
    app.state.settings_store = None
    app.state.cipher = None
    app.state.runtime = None
    app.state.call_recorder = None
    app.state.telegram_login = None

    with pytest.raises(APIError) as info:
        getter(_request(app))

    assert info.value.status_code == 503
    assert info.value.code == expected_code


def test_dependency_setelah_shutdown_juga_503(client: TestClient) -> None:
    """Tanpa lifespan, state di-*None*-kan; endpoint tidak boleh 500."""
    with pytest.raises(APIError) as info:
        get_database(_request(client.app))
    assert info.value.code == "database_unavailable"


# --------------------------------------------------------------- APIError


def test_payload_lengkap() -> None:
    payload = APIError(400, "bad_request", "Salah.", {"a": {"code": "x"}}).payload()
    assert payload == {
        "error": {
            "code": "bad_request",
            "message": "Salah.",
            "fields": {"a": {"code": "x"}},
        }
    }


def test_payload_tanpa_message_dan_fields() -> None:
    """Kode saja sudah cukup untuk UI menerjemahkan."""
    assert APIError(409, "conflict").payload() == {"error": {"code": "conflict"}}


def test_payload_fields_kosong_dihilangkan() -> None:
    assert "fields" not in APIError(409, "conflict", "Msg", {}).payload()["error"]


# -------------------------------------------------- validasi permintaan & setting


def test_validation_error_memetakan_lokasi_field(
    live_client: TestClient,
) -> None:
    res = live_client.post("/api/auth/login", json={"username": ""})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    # Lokasi dinormalisasi tanpa segmen `body` supaya stabil antar versi FastAPI.
    assert "username" in error["fields"]
    assert all(not key.startswith("body") for key in error["fields"])


def test_validation_error_selalu_punya_field(live_client: TestClient) -> None:
    """UI butuh kunci field yang bisa dipetakan ke input; tidak boleh kosong.

    Endpoint publik dipakai agar tes tidak terselubung autentikasi/CSRF.
    """
    res = live_client.post("/api/setup/admin", json={"username": "", "password": ""})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert error["fields"], "fields tidak boleh kosong untuk request validation"
    assert all(not key.startswith("body") for key in error["fields"])


def test_settings_validation_error_menghasilkan_fields_per_key(
    live_client: TestClient, csrf_of: Any
) -> None:
    """`PUT /settings` dengan nilai di luar rentang → 422 + rincian per setting."""
    from web_helpers import do_setup

    do_setup(live_client)
    res = live_client.put(
        "/api/settings",
        json={"changes": {"max_concurrent_calls": 0}},
        headers={"X-CSRF-Token": csrf_of(live_client)},
    )
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert "max_concurrent_calls" in error["fields"]


@pytest.fixture
def csrf_of() -> Any:
    from web_helpers import csrf_of as _csrf_of

    return _csrf_of