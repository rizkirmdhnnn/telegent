"""Kontrak frontend untuk Fase 4 / F2 (UI kontrol runtime).

Frontend belum punya runner unit (menunggu H2), jadi berkas ini menjaga hal yang
mudah rusak diam-diam dan murah diperiksa dari Python:

1. Komponen kontrol runtime & dialog konfirmasi benar-benar ada.
2. Tombol kendali memanggil endpoint F1 yang memang ada di backend.
3. Tidak ada warna hex hardcoded (Tailwind v4) dan tidak ada `fetch` mentah.
4. Kunci i18n yang dipakai F2 ada di **kedua** katalog.
5. Tidak ada lagi penanda "Segera" pada item nav yang phase-nya sudah selesai.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "frontend" / "src"
I18N_DIR = SRC_DIR / "lib" / "i18n"
ROUTER_RUNTIME = REPO_ROOT / "src" / "telegent" / "web" / "routers" / "runtime.py"

#: Berkas yang ditambahkan/diubah oleh F2.
FASE4_FILES = (
    "lib/components/runtime/RuntimeControl.svelte",
    "lib/components/ui/ConfirmDialog.svelte",
    "lib/components/settings/RestartPendingBar.svelte",
    "lib/stores/runtime.svelte.ts",
    "routes/(app)/+page.svelte",
    "routes/(app)/+layout.svelte",
    "routes/(app)/telegram/+page.svelte",
)

#: Aksi kendali yang harus punya komponen & pemanggilan endpoint.
RUNTIME_ACTIONS = ("start", "stop", "restart", "apply")

#: Warna hex tidak boleh dipakai (Tailwind v4 memakai palet slate/blue/amber).
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            flat.update(_flatten(value, f"{prefix}{key}."))
    else:
        flat[prefix.rstrip(".")] = data
    return flat


@pytest.fixture(scope="module")
def catalogs() -> dict[str, dict[str, str]]:
    return {
        name: _flatten(json.loads((I18N_DIR / f"{name}.json").read_text(encoding="utf-8")))
        for name in ("id", "en")
    }


@pytest.mark.parametrize("relative", FASE4_FILES)
def test_berkas_fase4_ada(relative: str) -> None:
    assert (SRC_DIR / relative).is_file(), f"{relative} belum dibuat"


def test_tidak_ada_warna_hex_hardcoded() -> None:
    offenders = [
        relative
        for relative in FASE4_FILES
        if HEX_COLOR.search((SRC_DIR / relative).read_text(encoding="utf-8"))
    ]
    assert not offenders, f"Warna hex hardcoded di: {offenders}"


def test_tidak_ada_fetch_mentah() -> None:
    """Semua mutasi lewat `apiFetch` agar header CSRF ikut terkirim."""
    store = (SRC_DIR / "lib/stores/runtime.svelte.ts").read_text(encoding="utf-8")
    assert not re.search(r"(?<![a-zA-Z])fetch\(", store), (
        "runtime store harus memakai apiFetch, bukan fetch langsung"
    )
    assert "apiFetch" in store


@pytest.mark.parametrize("action", RUNTIME_ACTIONS)
def test_aksi_kontrol_memakai_endpoint_yang_ada(action: str) -> None:
    """Endpoint yang dipanggil UI harus benar-benar terdaftar di router backend."""
    store = (SRC_DIR / "lib/stores/runtime.svelte.ts").read_text(encoding="utf-8")
    assert "`/runtime/${action}`" in store, f"store tidak memanggil /runtime/{action}"
    assert f'@router.post("/{action}")' in ROUTER_RUNTIME.read_text(encoding="utf-8"), (
        f"router backend tidak punya POST /runtime/{action}"
    )


def test_dialog_konfirmasi_menyebut_dampak() -> None:
    """Konfirmasi harus menyebut jumlah panggilan aktif yang diakhiri."""
    control = (SRC_DIR / "lib/components/runtime/RuntimeControl.svelte").read_text(
        encoding="utf-8"
    )
    assert "ConfirmDialog" in control
    assert "runtime.confirm_drain" in control
    assert "runtime.activeCalls" in control

    bar = (SRC_DIR / "lib/components/settings/RestartPendingBar.svelte").read_text(
        encoding="utf-8"
    )
    assert "ConfirmDialog" in bar
    assert "runtime.confirm_drain" in bar


def test_bar_restart_muncul_dari_status_runtime() -> None:
    """Bar memakai `pending_restart` dari status runtime, bukan state lokal."""
    bar = (SRC_DIR / "lib/components/settings/RestartPendingBar.svelte").read_text(
        encoding="utf-8"
    )
    assert "runtime.pendingKeys" in bar

    layout = (SRC_DIR / "routes/(app)/+layout.svelte").read_text(encoding="utf-8")
    assert "<RestartPendingBar />" in layout, "bar belum dipasang di app shell"


def test_kontrol_runtime_dipakai_di_dashboard_dan_shell() -> None:
    dashboard = (SRC_DIR / "routes/(app)/+page.svelte").read_text(encoding="utf-8")
    assert "RuntimeControl" in dashboard

    layout = (SRC_DIR / "routes/(app)/+layout.svelte").read_text(encoding="utf-8")
    assert "RuntimeControl" in layout


def test_error_runtime_punya_aksi_lanjutan() -> None:
    """`last_error` harus disertai arahkan: kredensial, login, atau jalankan bot."""
    control = (SRC_DIR / "lib/components/runtime/RuntimeControl.svelte").read_text(
        encoding="utf-8"
    )
    for key in ("runtime.fix_credentials", "runtime.fix_login", "runtime.fix_start"):
        assert key in control, f"aksi lanjutan {key} tidak dipakai"


@pytest.mark.parametrize("action", RUNTIME_ACTIONS)
def test_aksi_kontrol_punya_pesan_sukses(
    catalogs: dict[str, dict[str, str]], action: str
) -> None:
    """Semua aksi kendali harus punya kunci pesan sukses (aturan #1)."""
    for name, catalog in catalogs.items():
        assert f"runtime.{action}_done" in catalog, f"runtime.{action}_done hilang di {name}"


@pytest.mark.parametrize(
    "key",
    (
        "runtime.action_start",
        "runtime.action_stop",
        "runtime.action_restart",
        "runtime.confirm_drain",
        "runtime.confirm_no_active_calls",
        "runtime.confirm_stop_title",
        "runtime.confirm_restart_title",
        "runtime.confirm_apply_title",
        "runtime.confirm_cancel",
        "runtime.error_title",
        "runtime.fix_credentials",
        "runtime.fix_login",
        "runtime.fix_start",
        "dashboard.running_since",
    ),
)
def test_kunci_f2_ada_di_kedua_katalog(catalogs: dict[str, dict[str, str]], key: str) -> None:
    for name, catalog in catalogs.items():
        assert key in catalog, f"{key} hilang di {name}.json"


def test_nav_yang_sudah_jadi_tidak_ditandai_segera() -> None:
    """Item nav dengan halaman nyata tidak boleh memakai badge 'Segera'."""
    layout = (SRC_DIR / "routes/(app)/+layout.svelte").read_text(encoding="utf-8")
    for match in re.finditer(r"\{ href: '([^']+)'.*?soon:\s*(\w+)", layout):
        href, soon = match.group(1), match.group(2)
        if soon != "true":
            continue
        # Halaman audit belum dibuat (di luar cakupan F2) — sisanya harus punya halaman.
        assert href == "/audit", f"Item nav {href} masih ditandai Segera"


def test_store_menjaga_klik_ganda() -> None:
    """Permintaan kedua saat aksi berjalan harus diabaikan."""
    store = (SRC_DIR / "lib/stores/runtime.svelte.ts").read_text(encoding="utf-8")
    assert "if (this.busy) return false;" in store