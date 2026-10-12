"""Test CLI `telegent` (tiket G1): mode web (default) vs `--no-web` (headless).

Yang dijaga di sini adalah kontrak yang dipakai packaging & e2e:

- mode default **tidak** memanggil `Settings()` saat boot (panel harus hidup
  tanpa kredensial);
- `--no-web` mempertahankan perilaku lama: kredensial wajib, keluar dengan galat;
- `--host`/`--port` menimpa konfigurasi bootstrap.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

import telegent.__main__ as entry
from telegent.web.bootstrap import load_bootstrap

_ISOLATED_ENV_KEYS = (
    "TELEGENT_DATA_DIR",
    "TELEGENT_DB_URL",
    "TELEGENT_HOST",
    "TELEGENT_PORT",
    "TELEGENT_FAKE",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "GEMINI_API_KEY",
    "TELEGRAM_SESSION_DIR",
    "SESSION_DIR",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("telegent.web.bootstrap.load_dotenv", lambda *a, **k: False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Bersihkan environment agar hasil tes tidak bergantung pada shell developer."""
    for key in _ISOLATED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


class _FakeSettings:
    """`Settings` tiruan yang tidak butuh kredensial."""

    def __init__(self) -> None:
        self.allowed_user_ids = ""
        self.log_level = "INFO"


@pytest.fixture
def no_uvicorn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Ganti `uvicorn.run` dengan perekam; kembalikan daftar panggilan."""
    calls: list[dict[str, Any]] = []

    def _run(app: Any, **kwargs: Any) -> None:
        calls.append({"app": app, **kwargs})

    monkeypatch.setattr("uvicorn.run", _run)
    monkeypatch.setattr("telegent.web.app.create_app", lambda cfg: ("app", cfg))
    return calls


# ------------------------------------------------------------------- parser


def test_parser_bawaan_adalah_mode_web() -> None:
    args = entry._build_parser().parse_args([])
    assert args.no_web is False
    assert args.host is None
    assert args.port is None


def test_parser_no_web() -> None:
    assert entry._build_parser().parse_args(["--no-web"]).no_web is True


def test_parser_host_port_bisa_diberi() -> None:
    args = entry._build_parser().parse_args(["--host", "0.0.0.0", "--port", "9999"])
    assert args.host == "0.0.0.0"
    assert args.port == 9999


# ------------------------------------------------------------- mode headless


def test_headless_gagal_tanpa_kredensial(isolated_env: None) -> None:
    """Perilaku lama: tanpa kredensial, keluar dengan kode 1 (bukan boot web)."""
    assert entry._run_headless(entry._build_parser().parse_args(["--no-web"])) == 1


def test_headless_menerima_allow_user_berulang(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: dict[str, Any] = {}
    settings = _FakeSettings()

    class _App:
        def __init__(self, cfg: _FakeSettings) -> None:
            settings.allowed_user_ids = cfg.allowed_user_ids
            settings.log_level = cfg.log_level

        async def run(self) -> None:
            ran["yes"] = True

    monkeypatch.setattr(entry, "Settings", lambda: settings)
    monkeypatch.setattr(entry, "TelegentApp", _App)

    code = entry._run_headless(
        entry._build_parser().parse_args(
            ["--no-web", "--allow-user", "111", "--allow-user", "222", "--log-level", "DEBUG"]
        )
    )

    assert code == 0
    assert ran["yes"] is True
    assert settings.allowed_user_ids == "111,222"
    assert settings.log_level == "DEBUG"


def test_headless_galat_aplikasi_exit_1(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _App:
        def __init__(self, _cfg: Any) -> None:
            pass

        async def run(self) -> None:
            raise RuntimeError("gagal start")

    monkeypatch.setattr(entry, "Settings", lambda: _FakeSettings())
    monkeypatch.setattr(entry, "TelegentApp", _App)

    assert entry._run_headless(entry._build_parser().parse_args(["--no-web"])) == 1


def test_headless_keyboard_interrupt_exit_130(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _App:
        def __init__(self, _cfg: Any) -> None:
            pass

        async def run(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(entry, "Settings", lambda: _FakeSettings())
    monkeypatch.setattr(entry, "TelegentApp", _App)

    assert entry._run_headless(entry._build_parser().parse_args(["--no-web"])) == 130


# ----------------------------------------------------------------- mode web


def test_web_boot_tanpa_kredensial(
    isolated_env: None, no_uvicorn: list[dict[str, Any]]
) -> None:
    """Perangkap #1: panel boot walau `Settings()` tidak valid sama sekali.

    `Settings` sengaja tidak di-*stub* di tes ini — bila `_run_web` memakainya,
    panggilannya akan melempar dan tes gagal.
    """
    code = entry._run_web(entry._build_parser().parse_args([]))

    assert code == 0
    assert len(no_uvicorn) == 1
    assert no_uvicorn[0]["app"][0] == "app"


def test_web_host_port_menimpa_bootstrap(
    isolated_env: None, no_uvicorn: list[dict[str, Any]]
) -> None:
    entry._run_web(entry._build_parser().parse_args(["--host", "0.0.0.0", "--port", "9999"]))

    call = no_uvicorn[0]
    assert call["host"] == "0.0.0.0"
    assert call["port"] == 9999
    # Konfigurasi yang dipasang ke `create_app` ikut menyesuaikan.
    assert call["app"][1].host == "0.0.0.0"
    assert call["app"][1].port == 9999


def test_web_tanpa_flag_memakai_bootstrap_default(
    isolated_env: None, no_uvicorn: list[dict[str, Any]]
) -> None:
    entry._run_web(entry._build_parser().parse_args([]))

    assert no_uvicorn[0]["host"] == "127.0.0.1"
    assert no_uvicorn[0]["port"] == 8080


def test_web_allow_user_diabaikan_dengan_peringatan(
    isolated_env: None, no_uvicorn: list[dict[str, Any]], caplog: pytest.LogCaptureFixture
) -> None:
    """`--allow-user` tidak berlaku di mode web; harus diperingatkan, bukan diam."""
    with caplog.at_level("WARNING", logger="telegent"):
        entry._run_web(entry._build_parser().parse_args(["--allow-user", "111"]))

    assert any("allow-user" in record.getMessage() for record in caplog.records)


def test_web_galat_server_exit_1(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_app: Any, **_kwargs: Any) -> None:
        raise RuntimeError("bind gagal")

    monkeypatch.setattr("uvicorn.run", _boom)
    monkeypatch.setattr("telegent.web.app.create_app", lambda cfg: ("app", cfg))

    assert entry._run_web(entry._build_parser().parse_args([])) == 1


def test_web_keyboard_interrupt_exit_130(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_app: Any, **_kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("uvicorn.run", _boom)
    monkeypatch.setattr("telegent.web.app.create_app", lambda cfg: ("app", cfg))

    assert entry._run_web(entry._build_parser().parse_args([])) == 130


def test_web_mematikan_log_duplikat_uvicorn(
    isolated_env: None, no_uvicorn: list[dict[str, Any]]
) -> None:
    """Konfigurasi log bawaan uvicorn akan menggandakan setiap baris."""
    entry._run_web(entry._build_parser().parse_args([]))

    assert no_uvicorn[0]["log_config"] is None
    assert no_uvicorn[0]["access_log"] is False


# ------------------------------------------------------------------- main()


@pytest.mark.parametrize(
    ("argv", "expected_mode"),
    [(["telegent"], "web"), (["telegent", "--no-web"], "headless")],
)
def test_main_dispatch(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], expected_mode: str
) -> None:
    """`main()` memanggil mode yang sesuai lalu keluar lewat `_exit_cleanly`."""
    calls: list[str] = []
    monkeypatch.setattr(sys, "argv", argv)
    # Kode keluar dibuat berbeda per mode supaya tertukar routing-nya terdeteksi.
    codes = {"web": 7, "headless": 9}
    monkeypatch.setattr(entry, "_run_headless", lambda _a: calls.append("headless") or codes["headless"])
    monkeypatch.setattr(entry, "_run_web", lambda _a: calls.append("web") or codes["web"])
    monkeypatch.setattr(entry, "_exit_cleanly", lambda code: calls.append(f"exit:{code}"))

    entry.main()

    assert calls == [expected_mode, f"exit:{codes[expected_mode]}"]


def test_bootstrap_dibaca_dari_env(
    isolated_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TELEGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("TELEGENT_PORT", "7311")

    cfg = load_bootstrap()

    assert cfg.port == 7311
    assert cfg.data_dir == (tmp_path / "d").resolve()