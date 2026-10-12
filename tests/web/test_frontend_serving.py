"""Test penyajian hasil build frontend oleh FastAPI (tiket B1).

`frontend/build` adalah artefak hasil `npm run build` dan tidak ikut ter-commit,
jadi seluruh tes di berkas ini dilewati bila build belum tersedia.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from telegent.web.app import create_app
from telegent.web.bootstrap import load_bootstrap

REPO_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "build"

pytestmark = pytest.mark.skipif(
    not (REPO_FRONTEND_DIST / "index.html").is_file(),
    reason="frontend/build belum ada; jalankan `npm run build` di folder frontend",
)


@pytest.fixture
def client_with_frontend(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Client yang menyajikan SPA hasil build (bukan placeholder)."""
    cfg = load_bootstrap(data_dir=tmp_path / "data")
    assert cfg.has_frontend is True, "Build frontend harus tersedia di frontend/build"
    with TestClient(create_app(cfg)) as client:
        yield client


def test_serve_frontend_root(client_with_frontend: TestClient) -> None:
    res = client_with_frontend.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "<!doctype html>" in res.text.lower()


def test_serve_frontend_spa_fallback(client_with_frontend: TestClient) -> None:
    # Deep-link rute SPA harus menyajikan index.html
    res = client_with_frontend.get("/settings")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")


def test_api_tidak_tertangkap_fallback(client_with_frontend: TestClient) -> None:
    res = client_with_frontend.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"