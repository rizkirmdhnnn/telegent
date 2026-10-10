"""Helper pengujian web panel."""

from __future__ import annotations

from fastapi.testclient import TestClient

from telegent.web.security import CSRF_COOKIE

DEFAULT_PASSWORD = "rahasia-kuat-123"


def csrf_of(client: TestClient) -> str:
    """Token CSRF dari cookie (untuk header mutasi)."""
    token = client.cookies.get(CSRF_COOKIE)
    assert token, "cookie CSRF belum dipasang"
    return token


def do_setup(
    client: TestClient, username: str = "admin", password: str = DEFAULT_PASSWORD
) -> TestClient:
    """Jalankan wizard setup (admin langsung login)."""
    resp = client.post(
        "/api/setup/admin", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return client


def do_login(
    client: TestClient,
    username: str = "admin",
    password: str = DEFAULT_PASSWORD,
    **extra: object,
):
    """Kirim permintaan login (mengembalikan respons)."""
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password, **extra},
    )


def login(
    client: TestClient, username: str = "admin", password: str = DEFAULT_PASSWORD
) -> TestClient:
    """Login dan pastikan berhasil."""
    resp = do_login(client, username, password)
    assert resp.status_code == 200, resp.text
    return client