"""Entry point: `python -m telegent` atau console script `telegent`.

Dua mode:

- **default** — panel web + bot dalam satu proses. Panel tetap boot meski
  `Settings` belum valid (kredensial diisi dari panel), dan bot baru dijalankan
  bila kredensial + sesi Telegram sudah siap.
- **`--no-web`** — mode headless seperti versi sebelum web panel: bot langsung
  dijalankan dari environment dan keluar dengan galat bila kredensial tidak valid.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import os
import sys

from telegent import __version__
from telegent.app import TelegentApp
from telegent.config import Settings
from telegent.logging_setup import configure_logging, get_logger
from telegent.web.bootstrap import load_bootstrap


def _exit_cleanly(code: int) -> None:
    """Keluar tanpa memicu destruktor statis ntgcalls.

    `ntgcalls` (WebRTC C++) memanggil `abort()` di `__cxa_finalize` saat
    interpreter Python keluar (muncul sebagai SIGABRT/Abort trap di macOS).
    `os._exit` melewati finalisasi C/C++ tersebut. Semua resource aplikasi
    sudah ditutup lebih dulu di `TelegentApp._shutdown`.
    """
    try:
        logging.shutdown()  # flush handler log
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
    os._exit(code)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegent", description="Telegent - AI voice agent untuk panggilan Telegram"
    )
    parser.add_argument(
        "--allow-user",
        type=int,
        action="append",
        help="ID pengguna Telegram yang diizinkan menelepon (mode --no-web)",
    )
    parser.add_argument("--log-level", type=str, default=None, help="Override level log")
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Jalankan bot saja tanpa panel web (headless; untuk CI & container bot)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind host panel web (default: TELEGENT_HOST atau 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port panel web (default: TELEGENT_PORT atau 8080)",
    )
    parser.add_argument("--version", action="version", version=f"telegent {__version__}")
    return parser


def _run_headless(args: argparse.Namespace) -> int:
    """Mode bot saja: persis perilaku sebelum web panel (`--no-web`)."""
    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]  # dibaca dari env/.env
    except Exception as exc:  # noqa: BLE001
        print(f"Konfigurasi tidak valid: {exc}", file=sys.stderr)
        return 1

    if args.allow_user:
        settings.allowed_user_ids = ",".join(str(u) for u in args.allow_user)
    if args.log_level:
        settings.log_level = args.log_level

    configure_logging(settings.log_level)

    code = 0
    try:
        asyncio.run(TelegentApp(settings).run())
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:  # noqa: BLE001
        get_logger("telegent").exception("Berhenti karena error: %s", exc)
        code = 1
    return code


def _run_web(args: argparse.Namespace) -> int:
    """Mode panel web + bot dalam satu proses.

    `Settings` **tidak** dipakai untuk boot: panel harus tetap dapat dibuka walau
    kredensial belum terisi, karena admin justru perlu mengisinya lewat panel itu
    sendiri. Penolakan hanya terjadi saat bot benar-benar dijalankan, dan itu
    ditangani `SettingsStore.build_settings()` di dalam runtime.
    """
    cfg = load_bootstrap()
    if args.host:
        cfg = dataclasses.replace(cfg, host=args.host)
    if args.port:
        cfg = dataclasses.replace(cfg, port=args.port)

    level = args.log_level or os.getenv("LOG_LEVEL") or "INFO"
    configure_logging(level)

    if args.allow_user:
        get_logger("telegent").warning(
            "--allow-user diabaikan pada mode web; atur 'allowed_user_ids' dari panel."
        )

    # Impor lokal: modul web memuat FastAPI/uvicorn yang tidak dibutuhkan mode
    # headless.
    import uvicorn

    from telegent.web.app import create_app

    app = create_app(cfg)

    code = 0
    try:
        uvicorn.run(
            app,
            host=cfg.host,
            port=cfg.port,
            # Log dikelola `configure_logging` + handler panel; konfigurasi log
            # bawaan uvicorn akan menggandakan setiap baris.
            log_config=None,
            access_log=False,
        )
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:  # noqa: BLE001
        get_logger("telegent").exception("Berhenti karena error: %s", exc)
        code = 1
    return code


def main() -> None:
    args = _build_parser().parse_args()
    code = _run_headless(args) if args.no_web else _run_web(args)
    _exit_cleanly(code)


if __name__ == "__main__":
    main()