"""Konfigurasi logging terpusat dan logger berkonteks sesi."""

from __future__ import annotations

import logging

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Inisialisasi logging global (idempoten)."""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class _ContextAdapter(logging.LoggerAdapter):
    """LoggerAdapter yang menyisipkan prefix konteks (user/call) ke tiap pesan."""

    def process(self, msg, kwargs):  # type: ignore[override]
        prefix = self.extra.get("prefix", "") if self.extra else ""
        return f"{prefix}{msg}", kwargs


def call_logger(user_id: int, call_id: int) -> logging.LoggerAdapter:
    return _ContextAdapter(
        logging.getLogger("telegent.call"),
        {"prefix": f"[user={user_id} call={call_id}] "},
    )
