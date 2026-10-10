"""Fixture bersama untuk pengujian web panel."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from telegent.web.app import create_app
from telegent.web.bootstrap import BootstrapConfig, load_bootstrap


@pytest.fixture
def bootstrap(tmp_path: Path) -> BootstrapConfig:
    """Konfigurasi bootstrap terisolasi (data & DB di direktori sementara)."""
    return load_bootstrap(
        data_dir=tmp_path / "data",
        db_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )


@pytest.fixture
def app(bootstrap: BootstrapConfig) -> FastAPI:
    return create_app(bootstrap)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)