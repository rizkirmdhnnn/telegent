"""Pengujian API Settings (Tiket C1)."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient
from web_helpers import csrf_of, do_setup


def test_settings_unauthenticated(live_client: TestClient) -> None:
    resp = live_client.get("/api/settings")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


def test_settings_put_csrf_protected(live_client: TestClient) -> None:
    do_setup(live_client)
    resp = live_client.put(
        "/api/settings",
        json={"changes": {"max_concurrent_calls": 5}},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_get_settings_schema(live_client: TestClient) -> None:
    do_setup(live_client)
    resp = live_client.get("/api/settings/schema")
    assert resp.status_code == 200
    schema = resp.json()
    assert isinstance(schema, list)
    keys = {item["key"] for item in schema}
    assert "max_concurrent_calls" in keys
    assert "gemini_api_key" in keys
    assert "gemini_model" in keys


def test_get_settings_and_masking(live_client: TestClient) -> None:
    do_setup(live_client)
    resp = live_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    assert "pending_restart" in data
    assert isinstance(data["pending_restart"], bool)

    # Cek bahwa grup-grup muncul
    group_names = [g["group"] for g in data["groups"]]
    assert "model_ai" in group_names
    assert "kredensial" in group_names

    # Pastikan secret dimask
    for group in data["groups"]:
        for item in group["items"]:
            if item["secret"] and item["value"] is not None:
                assert item["value"].startswith("...") or item["value"] == ""


def test_put_settings_validation_error(live_client: TestClient) -> None:
    do_setup(live_client)
    token = csrf_of(live_client)
    resp = live_client.put(
        "/api/settings",
        json={"changes": {"max_concurrent_calls": -1}},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "validation_error"
    assert "max_concurrent_calls" in data["error"]["fields"]


def test_put_settings_hot_and_restart(live_client: TestClient) -> None:
    do_setup(live_client)
    token = csrf_of(live_client)

    # Ubah setting HOT (max_concurrent_calls) dan RESTART (telegram_session_name)
    resp = live_client.put(
        "/api/settings",
        json={
            "changes": {
                "max_concurrent_calls": 6,
                "telegram_session_name": "custom_session",
            }
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert "max_concurrent_calls" in result["applied"]
    assert "telegram_session_name" in result["needs_restart"]

    # Verifikasi status pending_restart
    get_resp = live_client.get("/api/settings")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["pending_restart"] is True
    assert "telegram_session_name" in get_data["pending_restart_keys"]


def test_log_level_langsung_berlaku_ke_logger_root(live_client: TestClient) -> None:
    """`log_level` mengatur logger root, bukan hanya bot.

    Tanpa ini, log INFO tidak pernah sampai ke `/logs/stream` karena logger root
    default Python adalah WARNING.
    """
    do_setup(live_client)
    root = logging.getLogger()
    sebelumnya = root.level
    try:
        resp = live_client.put(
            "/api/settings",
            json={"changes": {"log_level": "DEBUG"}},
            headers={"X-CSRF-Token": csrf_of(live_client)},
        )
        assert resp.status_code == 200
        assert root.level == logging.DEBUG

        live_client.put(
            "/api/settings",
            json={"changes": {"log_level": "ERROR"}},
            headers={"X-CSRF-Token": csrf_of(live_client)},
        )
        assert root.level == logging.ERROR
    finally:
        root.setLevel(sebelumnya)


def test_setting_lain_tidak_menyalakan_level_log(live_client: TestClient) -> None:
    do_setup(live_client)
    root = logging.getLogger()
    sebelumnya = root.level
    try:
        live_client.put(
            "/api/settings",
            json={"changes": {"max_concurrent_calls": 3}},
            headers={"X-CSRF-Token": csrf_of(live_client)},
        )
        assert root.level == sebelumnya
    finally:
        root.setLevel(sebelumnya)


def test_bus_log_menerima_level_info_setelah_boot(live_client: TestClient) -> None:
    """Setelah boot, log INFO harus benar-benar sampai ke ring buffer SSE."""
    do_setup(live_client)
    client: TestClient = live_client

    def publish() -> None:
        logging.getLogger("telegent.web.test").info("halo dari level info")

    # `set_root_level` dijalankan di lifespan; panggil publisher lewat portal
    # agar berjalan di event loop aplikasi.
    client.portal.call(publish)  # type: ignore[union-attr]

    entries = client.app.state.log_buffer.recent(limit=5)  # type: ignore[attr-defined]
    assert any(item["message"] == "halo dari level info" for item in entries)
