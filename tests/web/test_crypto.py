"""Test enkripsi secret & masking (tiket A3)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from telegent.web.bootstrap import load_bootstrap
from telegent.web.crypto import (
    SECRET_KEY_FILENAME,
    SecretCipher,
    SecretError,
    load_or_create_key,
    mask,
)


def test_kunci_dibuat_otomatis_dengan_izin_0600(tmp_path: Path) -> None:
    key = load_or_create_key(tmp_path / "data")
    key_path = tmp_path / "data" / SECRET_KEY_FILENAME

    assert key_path.is_file()
    assert Fernet(key)  # kunci valid
    mode = key_path.stat().st_mode
    assert stat.S_IMODE(mode) == 0o600


def test_kunci_dipakai_ulang_tidak_diregenerasi(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    first = load_or_create_key(data_dir)
    second = load_or_create_key(data_dir)
    assert first == second


def test_env_key_mendominasi_dan_tidak_membuat_berkas(tmp_path: Path) -> None:
    env_key = Fernet.generate_key().decode()
    key = load_or_create_key(tmp_path / "data", env_key)
    assert key == env_key.encode()
    assert not (tmp_path / "data" / SECRET_KEY_FILENAME).exists()


def test_round_trip_encrypt_decrypt(tmp_path: Path) -> None:
    cipher = SecretCipher.for_data_dir(tmp_path)
    token = cipher.encrypt("AIzaSy-rahasia")

    assert token != "AIzaSy-rahasia"
    assert cipher.decrypt(token) == "AIzaSy-rahasia"


def test_token_rusak_melempar_secret_error(tmp_path: Path) -> None:
    cipher = SecretCipher.for_data_dir(tmp_path)
    with pytest.raises(SecretError):
        cipher.decrypt("bukan-token-fernet")
    assert cipher.try_decrypt("bukan-token-fernet", default="fallback") == "fallback"
    assert cipher.try_decrypt("bukan-token-fernet") is None


def test_cipher_dari_bootstrap_menghormati_env(tmp_path: Path, monkeypatch) -> None:
    env_key = Fernet.generate_key().decode()
    monkeypatch.setenv("TELEGENT_SECRET_KEY", env_key)
    cfg = load_bootstrap(data_dir=tmp_path / "data")

    cipher = SecretCipher.from_bootstrap(cfg)
    assert cipher.decrypt(cipher.encrypt("rahasia")) == "rahasia"
    assert not (tmp_path / "data" / SECRET_KEY_FILENAME).exists()


def test_cipher_beda_data_dir_tidak_bisa_dekripsi(tmp_path: Path) -> None:
    a = SecretCipher.for_data_dir(tmp_path / "a")
    b = SecretCipher.for_data_dir(tmp_path / "b")
    with pytest.raises(SecretError):
        b.decrypt(a.encrypt("rahasia"))


@pytest.mark.parametrize(
    ("value", "harapan"),
    [
        (None, None),
        ("", ""),
        ("abc", "•••"),
        ("12345678", "••••••••"),
        ("AIzaSy1234567890abcd", "AIza••••••abcd"),
    ],
)
def test_mask(value: str | None, harapan: str | None) -> None:
    assert mask(value) == harapan


def test_mask_tidak_pernah_membocorkan_nilai_penuh() -> None:
    rahasia = "AIzaSy-super-rahasia-panjang"
    hasil = mask(rahasia)
    assert hasil is not None
    assert rahasia not in hasil
    assert hasil.startswith("AIza") and hasil.endswith(rahasia[-4:])