"""Pengujian API Kredensial (Tiket C3)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from web_helpers import csrf_of, do_setup


def test_update_telegram_credentials_csrf(live_client: TestClient) -> None:
    do_setup(live_client)
    resp = live_client.put(
        "/api/credentials/telegram",
        json={"api_id": 123456, "api_hash": "0123456789abcdef0123456789abcdef"},
    )
    assert resp.status_code == 403


def test_update_telegram_credentials_success(live_client: TestClient) -> None:
    do_setup(live_client)
    token = csrf_of(live_client)

    resp = live_client.put(
        "/api/credentials/telegram",
        json={"api_id": 98765432, "api_hash": "abcdef0123456789abcdef0123456789"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Cek pending restart di settings
    settings_resp = live_client.get("/api/settings")
    assert settings_resp.status_code == 200
    assert settings_resp.json()["pending_restart"] is True


def test_update_gemini_credentials_success(live_client: TestClient) -> None:
    do_setup(live_client)
    token = csrf_of(live_client)

    resp = live_client.put(
        "/api/credentials/gemini",
        json={"api_key": "AIzaSyFakeKeyWithMoreThanTwentyChars"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_secret_yang_tersimpan_tidak_ditimpa_bila_tidak_dikirim(
    live_client: TestClient,
) -> None:
    """UI tidak pernah menerima nilai secret; jadi payload kosong berarti "pertahankan"."""
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}

    live_client.put(
        "/api/credentials/telegram",
        json={"api_id": 111, "api_hash": "0123456789abcdef0123456789abcdef"},
        headers=headers,
    )
    live_client.put(
        "/api/credentials/gemini",
        json={"api_key": "AIzaSyAwal012345678901234567890"},
        headers=headers,
    )

    # Hanya api_id yang dikirim; api_hash harus tetap yang lama.
    resp = live_client.put("/api/credentials/telegram", json={"api_id": 222}, headers=headers)
    assert resp.status_code == 200

    settings = live_client.get("/api/settings").json()
    by_key = {item["key"]: item for g in settings["groups"] for item in g["items"]}
    assert by_key["telegram_api_id"]["value"] == 222
    # Nilainya tetap tersamar dan `is_set` — bukan berubah menjadi teks kosong.
    assert by_key["telegram_api_hash"]["is_set"] is True
    assert by_key["telegram_api_hash"]["value"] not in ("", None)
    assert by_key["gemini_api_key"]["is_set"] is True


def test_payload_kosong_ditolak(live_client: TestClient) -> None:
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}

    resp = live_client.put("/api/credentials/gemini", json={}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_changes"


def test_api_hash_memerlukan_32_karakter(live_client: TestClient) -> None:
    do_setup(live_client)
    headers = {"X-CSRF-Token": csrf_of(live_client)}

    resp = live_client.put(
        "/api/credentials/telegram", json={"api_hash": "pendek"}, headers=headers
    )
    assert resp.status_code == 422


def test_validate_credentials(live_client: TestClient) -> None:
    do_setup(live_client)
    token = csrf_of(live_client)

    # Saat belum diisi
    resp_tg_empty = live_client.post(
        "/api/credentials/validate",
        json={"kind": "telegram"},
    )
    assert resp_tg_empty.status_code == 200
    assert resp_tg_empty.json()["valid"] is False

    # Isi Telegram
    live_client.put(
        "/api/credentials/telegram",
        json={"api_id": 123456, "api_hash": "0123456789abcdef0123456789abcdef"},
        headers={"X-CSRF-Token": token},
    )

    # Validasi lagi
    resp_tg_ok = live_client.post(
        "/api/credentials/validate",
        json={"kind": "telegram"},
    )
    assert resp_tg_ok.status_code == 200
    assert resp_tg_ok.json()["valid"] is True

    # Validasi Gemini
    resp_gemini_empty = live_client.post(
        "/api/credentials/validate",
        json={"kind": "gemini"},
    )
    assert resp_gemini_empty.status_code == 200
    assert resp_gemini_empty.json()["valid"] is False

    # Isi Gemini
    live_client.put(
        "/api/credentials/gemini",
        json={"api_key": "AIzaSyValidLengthKey1234567890"},
        headers={"X-CSRF-Token": token},
    )

    resp_gemini_ok = live_client.post(
        "/api/credentials/validate",
        json={"kind": "gemini"},
    )
    assert resp_gemini_ok.status_code == 200
    assert resp_gemini_ok.json()["valid"] is True
