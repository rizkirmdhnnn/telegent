"""Kontrak katalog i18n (aturan rekayasa #1: `t()` saja, id & en sinkron).

Tiga hal yang dijaga di sini:

1. Kunci `id.json` dan `en.json` identik (pernah tidak sinkron di Fase 1).
2. Setiap kode galat yang dapat dikirim backend punya terjemahan `errors.<code>`.
3. Setiap kunci literal `t('...')`/`tParams('...')` di `.svelte` ada di kedua katalog.

Pemeriksaan tidak butuh Node maupun hasil build, jadi tetap jalan di CI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from telegent.web.telegram_login import (
    ACCOUNT_ERROR,
    ACCOUNT_LOGGED_IN,
    ACCOUNT_LOGGED_OUT,
    ACCOUNT_NOT_CONFIGURED,
    DEFAULT_MESSAGES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "frontend" / "src" / "lib" / "i18n"
SRC_DIR = REPO_ROOT / "src" / "telegent"
SVELTE_DIR = REPO_ROOT / "frontend" / "src"

#: Kode yang dikirim sebagai JSON mentah (bukan `APIError`) sehingga tidak
#: tertangkap regex di bawah, tapi tetap muncul sebagai `code` di respons.
_EXTRA_ERROR_CODES = {
    "validation_error",  # `errors.py` untuk validasi body
}

#: Status akun yang dipakai badge di halaman Telegram.
_ACCOUNT_STATUSES = (
    ACCOUNT_NOT_CONFIGURED,
    ACCOUNT_LOGGED_OUT,
    ACCOUNT_LOGGED_IN,
    ACCOUNT_ERROR,
)


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    """Ratakan katalog menjadi `{"a.b": nilai}`."""
    flat: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            flat.update(_flatten(value, f"{prefix}{key}."))
    else:
        flat[prefix.rstrip(".")] = data
    return flat


@pytest.fixture(scope="module")
def catalogs() -> dict[str, dict[str, Any]]:
    return {
        name: _flatten(json.loads((I18N_DIR / f"{name}.json").read_text(encoding="utf-8")))
        for name in ("id", "en")
    }


# ------------------------------------------------------- 1. paritas id vs en


def test_katalog_id_dan_en_memiliki_kunci_yang_identik(
    catalogs: dict[str, dict[str, Any]]
) -> None:
    id_keys = set(catalogs["id"])
    en_keys = set(catalogs["en"])

    assert not (id_keys - en_keys), f"Kunci hilang di en.json: {sorted(id_keys - en_keys)}"
    assert not (en_keys - id_keys), f"Kunci hilang di id.json: {sorted(en_keys - id_keys)}"


def test_semua_nilai_adalah_string(catalogs: dict[str, dict[str, Any]]) -> None:
    for name, catalog in catalogs.items():
        bukan_string = {key: value for key, value in catalog.items() if not isinstance(value, str)}
        assert not bukan_string, f"Nilai bukan string di {name}.json: {sorted(bukan_string)}"


# ------------------------------------------------- 2. kode galat backend → i18n


def test_semua_kode_galat_login_punya_terjemahan(
    catalogs: dict[str, dict[str, Any]]
) -> None:
    for code in DEFAULT_MESSAGES:
        for name, catalog in catalogs.items():
            assert f"errors.{code}" in catalog, f"errors.{code} tidak ada di {name}.json"


def test_kode_apierror_dipakai_di_sumber_punya_terjemahan(
    catalogs: dict[str, dict[str, Any]]
) -> None:
    """Setiap kode yang mungkin dikirim ke UI harus punya `errors.<code>`."""
    pola = re.compile(r'APIError\(\s*\d+\s*,\s*"([a-z_]+)"')
    pola_login = re.compile(r'TelegramLoginError\(\s*"([a-z_]+)"')

    kode: set[str] = set()
    for path in SRC_DIR.rglob("*.py"):
        teks = path.read_text(encoding="utf-8")
        kode.update(pola.findall(teks))
        kode.update(pola_login.findall(teks))
    kode.update(_EXTRA_ERROR_CODES)

    for code in sorted(kode):
        for name, catalog in catalogs.items():
            assert f"errors.{code}" in catalog, f"errors.{code} tidak ada di {name}.json"


def test_semua_status_akun_punya_label(catalogs: dict[str, dict[str, Any]]) -> None:
    """Badge status memakai `status.<kode>` secara dinamis — pastikan ada."""
    for status in _ACCOUNT_STATUSES:
        for name, catalog in catalogs.items():
            assert f"status.{status}" in catalog, f"status.{status} tidak ada di {name}.json"


# --------------------------------------------- 3. kunci literal di komponen


def _literal_keys(teks: str) -> set[str]:
    """Kunci `t('...')`/`tParams('...')` yang berupa literal (tanpa interpolasi)."""
    pola = re.compile(r"\bt(?:Params)?\(\s*'([a-z0-9_.]+)'")
    return set(pola.findall(teks))


def test_setiap_kunci_literal_di_svelte_ada_di_kedua_katalog(
    catalogs: dict[str, dict[str, Any]]
) -> None:
    hilang: dict[str, list[str]] = {"id": [], "en": []}
    for path in sorted(SVELTE_DIR.rglob("*.svelte")):
        for key in _literal_keys(path.read_text(encoding="utf-8")):
            for name, catalog in catalogs.items():
                if key not in catalog:
                    hilang[name].append(f"{path.relative_to(REPO_ROOT)}: {key}")

    for name, items in hilang.items():
        assert not items, f"Kunci tidak ada di {name}.json -> {sorted(set(items))}"