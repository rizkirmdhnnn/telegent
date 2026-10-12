"""Enkripsi secret (API key & api_hash) dan masking untuk UI/audit.

Kunci Fernet dibuat otomatis di `data/.secret_key` (izin 0600) bila belum ada dan
tidak diberikan lewat environment, sehingga tidak ada langkah CLI wajib.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("telegent.web.crypto")

SECRET_KEY_FILENAME = ".secret_key"
_KEY_PERMISSIONS = 0o600


class SecretError(RuntimeError):
    """Secret tidak dapat didekripsi (kunci salah atau data rusak)."""


def load_or_create_key(data_dir: Path, env_key: str | None = None) -> bytes:
    """Kunci enkripsi dari env, atau dari file (dibuat bila belum ada).

    `data_dir` dibuat bila belum ada. Berkas kunci ditulis dengan izin 0600.
    """
    if env_key and env_key.strip():
        return env_key.strip().encode("utf-8")

    data_dir.mkdir(parents=True, exist_ok=True)
    key_path = data_dir / SECRET_KEY_FILENAME

    if key_path.is_file():
        existing = key_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing.encode("utf-8")
        log.warning("Berkas kunci %s kosong; membuat kunci baru.", key_path)

    key = Fernet.generate_key()
    key_path.write_text(key.decode("utf-8"), encoding="utf-8")
    try:
        os.chmod(key_path, _KEY_PERMISSIONS)
    except OSError:  # pragma: no cover - bergantung pada filesystem
        log.warning("Gagal mengubah izin berkas kunci %s.", key_path)
    log.info("Kunci enkripsi dibuat di %s.", key_path)
    return key


def mask(value: object | None, *, keep: int = 4) -> str | None:
    """Tampilkan sebagian nilai untuk UI/audit tanpa membocorkan isi penuh."""
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return ""
    if len(stripped) <= keep * 2:
        return "•" * min(len(stripped), 8)
    return f"{stripped[:keep]}{'•' * 6}{stripped[-keep:]}"


class SecretCipher:
    """Pembungkus Fernet untuk enkripsi/dekripsi nilai secret."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_bootstrap(cls, config: object) -> "SecretCipher":
        """Buat cipher dari `BootstrapConfig` (data_dir + secret_key)."""
        data_dir = getattr(config, "data_dir")
        secret_key = getattr(config, "secret_key")
        return cls(load_or_create_key(Path(data_dir), secret_key))

    @classmethod
    def for_data_dir(cls, data_dir: Path, env_key: str | None = None) -> "SecretCipher":
        return cls(load_or_create_key(data_dir, env_key))

    def encrypt(self, plaintext: str) -> str:
        """Enkripsi nilai menjadi token yang aman disimpan di database."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Dekripsi token; melempar `SecretError` bila gagal."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise SecretError("Secret tidak dapat didekripsi.") from exc

    def try_decrypt(self, ciphertext: str, default: str | None = None) -> str | None:
        """Sama seperti `decrypt`, tetapi mengembalikan `default` bila gagal."""
        try:
            return self.decrypt(ciphertext)
        except SecretError:
            return default