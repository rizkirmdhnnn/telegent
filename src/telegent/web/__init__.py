"""Web panel Telegent: API + SPA dalam satu proses.

`create_app` diekspor secara lazy agar mengimpor `telegent.web` tidak ikut menarik
FastAPI (berguna untuk entry point headless dan pengujian unit).
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from telegent.web.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")