"""Kontrak frontend untuk Fase 3 (tiket E3).

Frontend tidak punya runner unit di fase ini (menunggu H2), jadi berkas ini
menjaga hal-hal yang mudah rusak diam-diam dan murah diperiksa dari Python:

1. Setiap halaman Fase 3 benar-benar ada dan mendaftarkan rute yang dijanjikan.
2. Tidak ada teks UI mentah di luar `t()` (aturan rekayasa #1).
3. Kunci i18n yang dipakai halaman memang ada di **kedua** katalog.
4. Klien SSE dan store pemantauan tidak memakai warna hardcoded di luar
   palet Tailwind yang sudah dipakai komponen lain.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from telegent.telegram.call_session import (
    END_REASON_AI,
    END_REASON_IDLE,
    END_REASON_MAX_DURATION,
    END_REASON_PANEL,
)
from telegent.web.call_store import ALL_OUTCOMES, END_REASON_CALLER, END_REASON_REJECTED

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "frontend" / "src"
I18N_DIR = SRC_DIR / "lib" / "i18n"


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


#: Halaman yang harus ada setelah Fase 3.
FASE3_PAGES = (
    "routes/(app)/+page.svelte",  # dashboard
    "routes/(app)/calls/+page.svelte",
    "routes/(app)/calls/[id]/+page.svelte",
    "routes/(app)/logs/+page.svelte",
)

#: Modul frontend yang ditambahkan di Fase 3.
FASE3_MODULES = (
    "lib/sse.ts",
    "lib/calls.ts",
    "lib/stores/monitoring.svelte.ts",
    "lib/stores/logs.svelte.ts",
    "lib/stores/calls.svelte.ts",
)

#: Semua `end_reason` yang bisa dikirim backend harus punya label.
ALL_END_REASONS = (
    END_REASON_CALLER,
    END_REASON_AI,
    END_REASON_MAX_DURATION,
    END_REASON_IDLE,
    END_REASON_PANEL,
    END_REASON_REJECTED,
    "error",
)

#: Status tool yang mungkin dikirim backend (spesifikasi §5.7).
ALL_TOOL_STATUSES = ("ok", "error", "timeout", "cancelled")

#: Pola warna hex yang tidak boleh dipakai (Tailwind v4 + palet slate).
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


@pytest.mark.parametrize("relative", FASE3_PAGES + FASE3_MODULES)
def test_berkas_fase3_ada(relative: str) -> None:
    assert (SRC_DIR / relative).is_file(), f"{relative} belum dibuat"


@pytest.mark.parametrize("outcome", ALL_OUTCOMES)
def test_setiap_outcome_punya_label(catalogs: dict[str, dict[str, str]], outcome: str) -> None:
    for name, catalog in catalogs.items():
        assert f"calls.outcome_{outcome}" in catalog, f"calls.outcome_{outcome} hilang di {name}"


@pytest.mark.parametrize("reason", ALL_END_REASONS)
def test_setiap_end_reason_punya_label(
    catalogs: dict[str, dict[str, str]], reason: str
) -> None:
    for name, catalog in catalogs.items():
        assert (
            f"calls.end_reason_{reason}" in catalog
        ), f"calls.end_reason_{reason} hilang di {name}"


@pytest.mark.parametrize("status", ALL_TOOL_STATUSES)
def test_setiap_status_tool_punya_label(
    catalogs: dict[str, dict[str, str]], status: str
) -> None:
    for name, catalog in catalogs.items():
        assert (
            f"calls.tool_status_{status}" in catalog
        ), f"calls.tool_status_{status} hilang di {name}"


def test_tidak_ada_warna_hex_hardcoded(catalogs: dict[str, dict[str, str]]) -> None:
    """Tailwind v4: warna lewat kelas, bukan hex (aturan rekayasa #8)."""
    offenders: list[str] = []
    for relative in FASE3_PAGES + FASE3_MODULES:
        text = (SRC_DIR / relative).read_text(encoding="utf-8")
        if HEX_COLOR.search(text):
            offenders.append(relative)
    assert not offenders, f"Warna hex hardcoded di: {offenders}"


def test_nav_panggilan_dan_log_tidak_lagi_segera() -> None:
    """Penanda 'Segera' pada Panggilan & Log harus hilang (E3)."""
    layout = (SRC_DIR / "routes/(app)/+layout.svelte").read_text(encoding="utf-8")
    for label in ("nav.calls", "nav.logs"):
        pattern = rf"label:\s*'{label}'[^\n]*soon:\s*(\w+)"
        match = re.search(pattern, layout)
        assert match is not None, f"item nav '{label}' tidak ditemukan"
        assert match.group(1) == "false", f"item nav '{label}' masih ditandai Segera"


def test_halaman_panggilan_tidak_memakai_fetch_mentah() -> None:
    """Semua permintaan HTTP lewat `apiFetch` (yang menambah header CSRF)."""
    for relative in ("routes/(app)/calls/+page.svelte", "routes/(app)/calls/[id]/+page.svelte"):
        text = (SRC_DIR / relative).read_text(encoding="utf-8")
        assert not re.search(r"(?<![a-zA-Z])fetch\(", text), (
            f"{relative} memakai fetch langsung; pakai apiFetch agar CSRF ikut"
        )
        assert "$lib/calls" in text or "$lib/stores/monitoring" in text, (
            f"{relative} harus memakai helper pemanggilan di $lib/calls"
        )


def test_endpoint_pemantauan_dipakai_frontend() -> None:
    """Frontend harus memanggil endpoint yang benar-benar ada di backend."""
    gabungan = "\n".join(
        (SRC_DIR / relative).read_text(encoding="utf-8")
        for relative in (
            "lib/calls.ts",
            "lib/sse.ts",
            "lib/stores/monitoring.svelte.ts",
            "lib/stores/calls.svelte.ts",
        )
    )

    for endpoint in (
        "/calls/active",
        "/calls?",
        "/calls/export",
        "/calls/${id}",
        "/transcript",
        "/tools",
        "/hangup",
    ):
        assert endpoint in gabungan, f"endpoint '{endpoint}' tidak dipakai frontend"

    assert "/api/events/stream" in gabungan
    assert "/api/logs/stream" in gabungan