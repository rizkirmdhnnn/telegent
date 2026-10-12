"""Test skeleton aplikasi web (tiket A1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from telegent import __version__
from telegent.web.app import create_app
from telegent.web.bootstrap import DEFAULT_PORT, BootstrapConfig, load_bootstrap

_BOOTSTRAP_ENV_KEYS = (
    "TELEGENT_DATA_DIR",
    "TELEGENT_DB_URL",
    "TELEGENT_HOST",
    "TELEGENT_PORT",
    "TELEGENT_SESSION_TTL_HOURS",
    "TELEGENT_AUTOSTART_BOT",
    "TELEGENT_SECRET_KEY",
    "TELEGENT_FRONTEND_DIST",
)


def test_create_app_menempelkan_bootstrap(app: FastAPI, bootstrap: BootstrapConfig) -> None:
    assert app.state.bootstrap is bootstrap


def test_healthz_publik(client: TestClient) -> None:
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["version"] == __version__
    # Di luar lifespan, database belum disiapkan.
    assert body["db"] == "not_started"


def test_healthz_melaporkan_database_siap(bootstrap: BootstrapConfig) -> None:
    with TestClient(create_app(bootstrap)) as client:
        assert client.get("/api/healthz").json()["db"] == "ok"


def test_root_menampilkan_placeholder(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Telegent Web Panel" in resp.text


def test_routing_spa_fallback(client: TestClient) -> None:
    """Deep-link SPA dilayani placeholder/index, bukan 404 JSON."""
    assert client.get("/settings/telegram").status_code == 200


def test_api_tidak_dikenal_mengembalikan_json_404(client: TestClient) -> None:
    resp = client.get("/api/tidak-ada")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_berkas_hilang_dengan_ekstensi_mengembalikan_404(client: TestClient) -> None:
    assert client.get("/favicon.ico").status_code == 404


def test_header_keamanan_ditambahkan(client: TestClient) -> None:
    headers = client.get("/api/healthz").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_lifespan_membuat_direktori_data(bootstrap: BootstrapConfig) -> None:
    assert not bootstrap.data_dir.exists()
    with TestClient(create_app(bootstrap)) as client:
        assert bootstrap.data_dir.is_dir()
        assert client.get("/api/healthz").status_code == 200


def test_load_bootstrap_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _BOOTSTRAP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    cfg = load_bootstrap()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == DEFAULT_PORT
    assert cfg.autostart_bot is True
    assert cfg.secret_key is None
    assert cfg.data_dir.name == "data"
    assert cfg.db_url.endswith("telegent.db")
    # Bergantung pada apakah build frontend sudah ada; yang dijamin adalah
    # `has_frontend` konsisten dengan keberadaan index.html di dist.
    assert cfg.has_frontend == (cfg.frontend_dist / "index.html").is_file()


def test_load_bootstrap_dan_override_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _BOOTSTRAP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TELEGENT_PORT", "9999")
    monkeypatch.setenv("TELEGENT_AUTOSTART_BOT", "no")
    monkeypatch.setenv("TELEGENT_SECRET_KEY", "abc")
    monkeypatch.setenv("TELEGENT_SESSION_TTL_HOURS", "24")

    cfg = load_bootstrap(data_dir=tmp_path / "d")
    assert cfg.port == 9999
    assert cfg.autostart_bot is False
    assert cfg.secret_key == "abc"
    assert cfg.session_ttl_hours == 24
    assert cfg.data_dir == (tmp_path / "d").resolve()
    assert cfg.db_path == (tmp_path / "d" / "telegent.db")


def test_nilai_env_tidak_valid_kembali_ke_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGENT_PORT", "bukan-angka")
    monkeypatch.setenv("TELEGENT_SESSION_TTL_HOURS", "")
    cfg = load_bootstrap()
    assert cfg.port == DEFAULT_PORT
    assert cfg.session_ttl_hours == 168


def test_frontend_dist_ditemukan_bila_build_ada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dist = tmp_path / "build"
    dist.mkdir()
    (dist / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    monkeypatch.setenv("TELEGENT_FRONTEND_DIST", str(dist))

    cfg = load_bootstrap()
    assert cfg.has_frontend is True
    assert cfg.frontend_dist == dist

    app = create_app(cfg)
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "ok" in resp.text
        # Aset di dalam dist dilayani langsung.
        assert client.get("/index.html").status_code == 200