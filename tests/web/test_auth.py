"""Test autentikasi admin, setup, CSRF, dan TOTP (tiket A5)."""

from __future__ import annotations

import re
from datetime import timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from web_helpers import csrf_of, do_login, do_setup
from sqlalchemy import select

from telegent.web.bootstrap import BootstrapConfig
from telegent.web.crypto import SecretCipher
from telegent.web.db import models
from telegent.web.db.base import Database, utcnow
from telegent.web.security import (
    CSRF_COOKIE,
    LOCKOUT_MINUTES,
    MAX_FAILED_ATTEMPTS,
    MIN_PASSWORD_LENGTH,
    SESSION_COOKIE,
    SessionManager,
    hash_password,
    password_problem,
    verify_password,
    verify_totp,
)

PASSWORD = "rahasia-kuat-123"


@pytest.fixture
def prepared(live_client: TestClient) -> TestClient:
    """Client yang sudah punya admin tapi belum login."""
    do_setup(live_client)
    live_client.post("/api/auth/logout")
    return live_client


# -------------------------------------------------------------------- setup


def test_status_menunjukkan_butuh_setup(live_client: TestClient) -> None:
    assert live_client.get("/api/setup/status").json() == {"needs_setup": True}


def test_membuat_admin_dan_langsung_login(live_client: TestClient) -> None:
    do_setup(live_client)
    assert live_client.get("/api/setup/status").json() == {"needs_setup": False}
    assert SESSION_COOKIE in live_client.cookies
    assert live_client.get("/api/auth/me").json()["username"] == "admin"


def test_setup_ditolak_bila_admin_sudah_ada(live_client: TestClient) -> None:
    do_setup(live_client)
    resp = live_client.post(
        "/api/setup/admin", json={"username": "lain", "password": PASSWORD}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "already_setup"


def test_setup_menolak_password_pendek(live_client: TestClient) -> None:
    resp = live_client.post(
        "/api/setup/admin", json={"username": "admin", "password": "pendek"}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "password_too_short"


async def test_password_disimpan_sebagai_hash(
    live_client: TestClient, bootstrap: BootstrapConfig
) -> None:
    do_setup(live_client)

    db = Database(bootstrap.db_url)
    try:
        async with db.session() as session:
            row = (await session.execute(select(models.AdminUser))).scalars().one()
            stored = row.password_hash
    finally:
        await db.dispose()

    assert stored.startswith("$argon2")
    assert PASSWORD not in stored
    assert verify_password(stored, PASSWORD) is True


# -------------------------------------------------------------------- login


def test_login_dan_logout(prepared: TestClient) -> None:
    resp = do_login(prepared)
    assert resp.status_code == 200
    assert prepared.get("/api/auth/me").status_code == 200

    assert prepared.post("/api/auth/logout").status_code == 200
    assert prepared.get("/api/auth/me").status_code == 401


def test_login_salah_gagal(prepared: TestClient) -> None:
    resp = do_login(prepared, password="salah-total")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_login_tidak_dikenal(prepared: TestClient) -> None:
    resp = do_login(prepared, username="entah")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_lockout_setelah_beberapa_kegagalan(prepared: TestClient) -> None:
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        assert do_login(prepared, password="salah").status_code == 401

    resp = do_login(prepared, password="salah")
    assert resp.status_code == 423
    assert resp.json()["error"]["code"] == "locked"

    # Bahkan password benar ditolak selama terkunci.
    assert do_login(prepared).status_code == 423


async def test_lockout_bisa_pulih_setelah_waktu(live_client: TestClient) -> None:
    do_setup(live_client)
    live_client.post("/api/auth/logout")
    for _ in range(MAX_FAILED_ATTEMPTS):
        do_login(live_client, password="salah")

    db = Database(live_client.app.state.bootstrap.db_url)  # type: ignore[attr-defined]
    try:
        async with db.session() as session:
            row = (await session.execute(select(models.AdminUser))).scalars().one()
            row.locked_until = utcnow() - timedelta(seconds=1)
    finally:
        await db.dispose()

    assert do_login(live_client).status_code == 200


def test_me_menolak_tanpa_sesi(live_client: TestClient) -> None:
    assert live_client.get("/api/auth/me").status_code == 401


def test_sesi_kedaluwarsa_ditolak() -> None:
    manager = SessionManager(ttl_hours=1)
    session = manager.create("admin", 1)
    assert manager.get(session.token) is session

    session.expires_at = utcnow() - timedelta(seconds=1)
    assert manager.get(session.token) is None


# ---------------------------------------------------------------------- CSRF


def test_mutasi_tanpa_csrf_ditolak(prepared: TestClient) -> None:
    do_login(prepared)
    resp = prepared.patch("/api/auth/me", json={"locale": "en"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_csrf_salah_ditolak(prepared: TestClient) -> None:
    do_login(prepared)
    resp = prepared.patch(
        "/api/auth/me", json={"locale": "en"}, headers={"X-CSRF-Token": "ngawur"}
    )
    assert resp.status_code == 403


def test_mutasi_dengan_csrf_berhasil(prepared: TestClient) -> None:
    do_login(prepared)
    resp = prepared.patch(
        "/api/auth/me", json={"locale": "en", "theme": "dark"}, headers={"X-CSRF-Token": csrf_of(prepared)}
    )
    assert resp.status_code == 200
    assert prepared.get("/api/auth/me").json() == {
        "username": "admin",
        "totp_enabled": False,
        "locale": "en",
        "theme": "dark",
    }


def test_bahasa_dan_tema_tidak_valid(prepared: TestClient) -> None:
    do_login(prepared)
    headers = {"X-CSRF-Token": csrf_of(prepared)}
    assert prepared.patch("/api/auth/me", json={"locale": "fr"}, headers=headers).status_code == 422
    assert prepared.patch("/api/auth/me", json={"theme": "neon"}, headers=headers).status_code == 422


# ------------------------------------------------------------------ password


def test_ganti_password(prepared: TestClient) -> None:
    do_login(prepared)
    headers = {"X-CSRF-Token": csrf_of(prepared)}

    assert prepared.post(
        "/api/auth/password", json={"current": "salah", "new": "baru-kuat-456"}, headers=headers
    ).status_code == 401

    assert prepared.post(
        "/api/auth/password", json={"current": PASSWORD, "new": "baru-kuat-456"}, headers=headers
    ).status_code == 200

    prepared.post("/api/auth/logout")
    assert do_login(prepared, password="baru-kuat-456").status_code == 200


def test_password_baru_terlalu_pendek(prepared: TestClient) -> None:
    do_login(prepared)
    resp = prepared.post(
        "/api/auth/password",
        json={"current": PASSWORD, "new": "pendek"},
        headers={"X-CSRF-Token": csrf_of(prepared)},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "password_too_short"


# ---------------------------------------------------------------------- TOTP


def test_alur_totp_lengkap(prepared: TestClient) -> None:
    do_login(prepared)
    headers = {"X-CSRF-Token": csrf_of(prepared)}

    setup = prepared.post("/api/auth/totp/setup", headers=headers)
    assert setup.status_code == 200
    body = setup.json()
    secret = body["secret"]
    assert body["otpauth_uri"].startswith("otpauth://totp/Telegent")
    assert "<svg" in body["qr_svg"]

    assert prepared.post("/api/auth/totp/enable", json={"code": "000000"}, headers=headers).status_code == 401

    assert prepared.post(
        "/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers
    ).status_code == 200
    assert prepared.get("/api/auth/me").json()["totp_enabled"] is True

    # Login berikutnya menuntut kode.
    prepared.post("/api/auth/logout")
    assert do_login(prepared).status_code == 401  # tanpa kode
    assert do_login(prepared, totp="111111").status_code == 401
    assert do_login(prepared, totp=pyotp.TOTP(secret).now()).status_code == 200

    # Matikan lagi.
    headers = {"X-CSRF-Token": csrf_of(prepared)}
    assert prepared.post(
        "/api/auth/totp/disable", json={"code": pyotp.TOTP(secret).now()}, headers=headers
    ).status_code == 200
    prepared.post("/api/auth/logout")
    assert do_login(prepared).status_code == 200


def test_totp_enable_tanpa_setup_ditolak(prepared: TestClient) -> None:
    do_login(prepared)
    resp = prepared.post(
        "/api/auth/totp/enable", json={"code": "123456"}, headers={"X-CSRF-Token": csrf_of(prepared)}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "totp_not_setup"


def test_totp_disable_saat_tidak_aktif(prepared: TestClient) -> None:
    do_login(prepared)
    resp = prepared.post(
        "/api/auth/totp/disable", json={"code": "123456"}, headers={"X-CSRF-Token": csrf_of(prepared)}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "totp_not_enabled"


async def test_secret_totp_tersimpan_terenkripsi(
    live_client: TestClient, bootstrap: BootstrapConfig
) -> None:
    do_setup(live_client)
    live_client.post("/api/auth/totp/setup", headers={"X-CSRF-Token": csrf_of(live_client)})

    db = Database(bootstrap.db_url)
    try:
        async with db.session() as session:
            row = (await session.execute(select(models.AdminUser))).scalars().one()
            stored = row.totp_secret_enc
    finally:
        await db.dispose()

    assert stored is not None
    assert re.fullmatch(r"[A-Z2-7]+=*", stored) is None  # bukan secret TOTP base32
    assert SecretCipher.for_data_dir(bootstrap.data_dir).try_decrypt(stored)


# ------------------------------------------------------------------ security


def test_password_hash_dan_verifikasi() -> None:
    hashed = hash_password(PASSWORD)
    assert PASSWORD not in hashed
    assert verify_password(hashed, PASSWORD) is True
    assert verify_password(hashed, "lain") is False
    assert verify_password("bukan-hash", PASSWORD) is False


def test_password_problem() -> None:
    assert password_problem("pendek") == "password_too_short"
    assert password_problem("cukup-panjang-123") is None
    assert MIN_PASSWORD_LENGTH == 8


def test_verify_totp_menolak_kode_kosong_atau_ngawur() -> None:
    secret = pyotp.random_base32()
    assert verify_totp(secret, "") is False
    assert verify_totp(secret, "abcd") is False
    assert verify_totp(secret, pyotp.TOTP(secret).now()) is True


def test_lockout_menggunakan_konstanta_yang_teruji() -> None:
    assert (MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES) == (5, 15)


def test_sanitasi_cookie_httponly_lengkap(live_client: TestClient) -> None:
    """Pastikan header Set-Cookie sesi menandai HttpOnly (dicek lewat respons)."""
    do_setup(live_client)
    resp = do_login(live_client)
    headers = resp.headers.get_list("set-cookie")
    session_cookie = next(h for h in headers if h.startswith(f"{SESSION_COOKIE}="))
    csrf_cookie = next(h for h in headers if h.startswith(f"{CSRF_COOKIE}="))
    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "samesite=lax" in session_cookie.lower()