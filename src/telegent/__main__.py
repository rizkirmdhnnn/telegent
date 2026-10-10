"""Entry point: `python -m telegent` atau console script `telegent`."""

from __future__ import annotations

import argparse
import asyncio
import sys

from telegent import __version__
from telegent.app import TelegentApp
from telegent.config import Settings
from telegent.logging_setup import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="telegent", description="Telegent - AI voice agent untuk panggilan Telegram"
    )
    parser.add_argument(
        "--allow-user",
        type=int,
        action="append",
        help="ID pengguna Telegram yang diizinkan menelepon (boleh berulang)",
    )
    parser.add_argument("--log-level", type=str, default=None, help="Override level log")
    parser.add_argument("--version", action="version", version=f"telegent {__version__}")
    args = parser.parse_args()

    try:
        settings = Settings()  # pyright: ignore[reportCallIssue]  # dibaca dari env/.env
    except Exception as exc:  # noqa: BLE001
        print(f"Konfigurasi tidak valid: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if args.allow_user:
        settings.allowed_user_ids = ",".join(str(u) for u in args.allow_user)
    if args.log_level:
        settings.log_level = args.log_level

    configure_logging(settings.log_level)

    try:
        asyncio.run(TelegentApp(settings).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
