"""Test tambahan keamanan: cookie sesi, TTL sesi, kunci enkripsi, dan helper.

Berkas ini melengkapi `test_auth.py` dan `test_crypto.py` pada cabang yang
belum tersentuh: masa berlaku sesi, attribute cookie, berkas kunci yang rusak,
dan batas ukuran JSON yang protecting database.
"""

from __future__ import annotations

import os
import stat
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from telegent.web.call_store import MAX_JSON_LEN, dumps_json
from telegent.web.crypto import (
    SECRET_KEY_FILENAME,
    SecretCipher,
    SecretError,
    load_or_create_key,
    mask,
)
from telegent.web.db.base import utcnow
from telegent.web.security import (
    CSRF_COOKIE,
    LOCKOUT_MINUTES,
    MAX_FAILED_ATTEMPTS,
    MIN_PASSWORD_LENGTH,
    SESSION_COOKIE,
    SessionManager,
    generate_totp_secret,
    hash_password,
    password_problem,
    set_session_cookies,
    totp_uri,
    verify_password,
    verify_totp,
)


# ------------------------------------------------------------- password


def test_password_hash_tidak_simpan_plain() -> None:
    digest = hash_password("rahasia-kuat-123")
    assert "rahasia-kuat-123" not in digest


def test_verify_password_menolak_hash_rusak() -> None:
    """Hash korup harus dianggap gagal, bukan melempar 500."""
    assert verify_password("bukan-hash-argon2", "apa-saja") is False


def test_password_problem_melaporkan_kode() -> None:
    assert password_problem("pendek") == "password_too_short"
    assert password_problem("x" * (MIN_PASSWORD_LENGTH - 1)) == "password_too_short"
    assert password_problem("x" * MIN_PASSWORD_LENGTH) is None


# ---------------------------------------------------------- SessionManager


def test_sesi_kedaluwarsa_otomatis_dibuang() -> None:
    manager = SessionManager(ttl_hours=1)
    session = manager.create("admin", 1)
    session.expires_at = utcnow() - timedelta(seconds=1)

    assert manager.get(session.token) is None
    assert manager.active_count == 0


def test_purge_expired_mengembalikan_jumlah() -> None:
    manager = SessionManager(ttl_hours=1)
    hidup = manager.create("admin", 1)
    basi = manager.create("admin", 1)
    basi.expires_at = utcnow() - timedelta(seconds=1)

    assert manager.purge_expired() == 1
    assert manager.get(hidup.token) is not None
    assert manager.purge_expired() == 0


@pytest.mark.parametrize("ttl", [0, -5])
def test_ttl_dijepit_minimal_satu_jam(ttl: int) -> None:
    """TTL 0/negatif tidak boleh membuat sesi langsung kedaluwarsa."""
    manager = SessionManager(ttl_hours=ttl)
    session = manager.create("admin", 1)
    assert session.expired is False


def test_delete_none_aman() -> None:
    manager = SessionManager(ttl_hours=1)
    manager.delete(None)
    manager.delete("token-tidak-ada")


def test_get_token_kosong_aman() -> None:
    manager = SessionManager(ttl_hours=1)
    assert manager.get(None) is None
    assert manager.get("") is None


# ------------------------------------------------------------------ cookie


def _cookie_header(response: Any, name: str) -> str:
    """Nilai header `Set-Cookie` milik satu cookie (satu cookie per baris)."""
    for value in response.headers.get_list("set-cookie"):
        if value.startswith(f"{name}="):
            return value
    raise AssertionError(f"cookie {name} tidak ditemukan")


def _setup_response(live_client: TestClient) -> Any:
    """Respons setup: satu-satunya respons yang memasang kedua cookie."""
    res = live_client.post(
        "/api/setup/admin", json={"username": "admin", "password": "rahasia-kuat-123"}
    )
    assert res.status_code == 200, res.text
    return res


def test_cookie_sesi_attribute_lengkap(live_client: TestClient) -> None:
    """`httpOnly` menjaga cookie dari JS; `SameSite` menutup celah CSRF sederhana."""
    res = _setup_response(live_client)

    sesi = _cookie_header(res, SESSION_COOKIE)
    assert "HttpOnly" in sesi
    assert "samesite=lax" in sesi.lower()
    assert "Path=/" in sesi

    csrf = _cookie_header(res, CSRF_COOKIE)
    assert "HttpOnly" not in csrf  # SPA harus bisa membacanya


def test_max_age_sesuai_ttl(live_client: TestClient) -> None:
    res = _setup_response(live_client)
    header = _cookie_header(res, SESSION_COOKIE)
    assert "Max-Age=604800" in header  # 168 jam × 3600


def test_clear_session_cookies_hapus_keduanya() -> None:
    from starlette.responses import Response

    from telegent.web.security import clear_session_cookies

    response = Response()
    set_session_cookies(response, "token", "csrf", 1)
    clear_session_cookies(response)

    deleted = [v.decode() for k, v in response.raw_headers if k.lower() == b"set-cookie"]
    assert any(v.startswith(f"{SESSION_COOKIE}=") for v in deleted)
    assert any(v.startswith(f"{CSRF_COOKIE}=") for v in deleted)


def test_cookie_tidak_pakai_flag_secure(live_client: TestClient) -> None:
    """Cookie sengaja tanpa flag `Secure` agar tetap jalan di HTTP lokal (spec §9)."""
    res = _setup_response(live_client)
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        header = _cookie_header(res, name)
        assert "secure" not in header.lower()


# --------------------------------------------------------------------- TOTP


def test_totp_roundtrip() -> None:
    import pyotp

    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code) is True


def test_totp_kode_kosong_ditolak() -> None:
    assert verify_totp(generate_totp_secret(), "") is False
    assert verify_totp(generate_totp_secret(), "   ") is False


def test_totp_kode_salah_ditolak() -> None:
    assert verify_totp(generate_totp_secret(), "000000") is False


def test_totp_uri_memuat_issuer_dan_nama() -> None:
    uri = totp_uri(generate_totp_secret(), "admin")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=Telegent" in uri


# ------------------------------------------------------- kunci enkripsi


def test_kunci_dibuat_dengan_izin_0600(tmp_path: Path) -> None:
    load_or_create_key(tmp_path)
    izin = stat.S_IMODE(os.stat(tmp_path / SECRET_KEY_FILENAME).st_mode)
    assert izin == 0o600


def test_kunci_dipakai_ulang_jika_sudah_ada(tmp_path: Path) -> None:
    """Kunci lama harus dipakai apa adanya — dibuat ulang = secret tak terbaca."""
    first = load_or_create_key(tmp_path)
    second = load_or_create_key(tmp_path)
    assert first == second


def test_kunci_kosong_dibuat_ulang(tmp_path: Path) -> None:
    """Berkas kunci yang kosong tidak boleh dipakai: dekripsi akan selalu gagal."""
    key_file = tmp_path / SECRET_KEY_FILENAME
    key_file.write_text("", encoding="utf-8")

    key = load_or_create_key(tmp_path)

    assert key.strip()
    SecretCipher(key)  # kunci valid, tidak melempar


def test_env_key_mengbeats_berkas(tmp_path: Path) -> None:
    """`TELEGENT_SECRET_KEY` adalah sumber tertinggi (mis. restore backup)."""
    from_file = load_or_create_key(tmp_path)
    from_env = load_or_create_key(tmp_path, env_key="kunci-dari-env")

    assert from_env == b"kunci-dari-env"
    assert from_file != from_env


def test_env_key_kosong_diabaikan(tmp_path: Path) -> None:
    assert load_or_create_key(tmp_path, env_key="   ") == load_or_create_key(tmp_path)


def test_secret_terenkripsi_tidak_bocor(tmp_path: Path) -> None:
    cipher = SecretCipher.for_data_dir(tmp_path)
    token = cipher.encrypt("AIzaSyRahasia")
    assert "AIzaSyRahasia" not in token
    assert cipher.decrypt(token) == "AIzaSyRahasia"


def test_decrypt_gagal_ditangani_elper(tmp_path: Path) -> None:
    """`try_decrypt` mengembalikan default, bukan melempar ke handler."""
    cipher = SecretCipher.for_data_dir(tmp_path)
    assert cipher.try_decrypt("bukan-token") is None
    assert cipher.try_decrypt("bukan-token", default="") == ""
    with pytest.raises(SecretError):
        cipher.decrypt("bukan-token")


def test_mask_tidak_membocorkan_nilai_penuh() -> None:
    assert mask("AIzaSy0123456789abcdefghijklmnop") == "AIza••••••mnop"
    assert mask(None) is None
    assert mask("") == ""
    assert mask("   ") == ""
    # Nilai pendek disamarkan penuh.
    assert mask("abc") == "•••"


# ------------------------------------------------------------- batas JSON


def test_dumps_json_normal() -> None:
    assert dumps_json({"a": 1}) == '{"a": 1}'


def test_dumps_json_none_kosong() -> None:
    assert dumps_json(None) is None


def test_dumps_json_memotong_nilai_besar() -> None:
    hasil = dumps_json({"teks": "x" * (MAX_JSON_LEN + 100)})
    assert hasil is not None
    assert len(hasil) <= MAX_JSON_LEN + 1
    assert hasil.endswith("…")


def test_dumps_json_nilai_tidak_bisa_disialisasi() -> None:
    """Bytes tidak bisa di-`json.dumps`; harus jatuh ke `str`, bukan exception."""
    assert dumps_json(b"data-mentah") is not None


# ------------------------------------------------------------- lockout login


def test_konstanta_lockout_konsisten_dengan_router() -> None:
    from telegent.web.routers import auth as auth_router

    assert auth_router.MAX_FAILED_ATTEMPTS == MAX_FAILED_ATTEMPTS
    assert auth_router.LOCKOUT_MINUTES == LOCKOUT_MINUTES