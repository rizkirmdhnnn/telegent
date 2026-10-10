"""Aplikasi FastAPI: menyajikan API web dan SPA dalam satu proses.

`create_app()` menyatukan control plane (API) dengan runtime bot. Komponen database
(A2), event bus (A8), dan runtime controller (A7) dipasang pada `lifespan`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, cast

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from telegent import __version__
from telegent.web.bootstrap import BootstrapConfig, load_bootstrap
from telegent.web.crypto import SecretCipher
from telegent.web.db import Database
from telegent.web.db.migrate import upgrade_to_head_async
from telegent.web.routers import ROUTERS
from telegent.web.settings_store import SettingsStore

log = logging.getLogger("telegent.web")

API_PREFIX = "/api"

_PLACEHOLDER_HTML = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telegent Web Panel</title>
</head>
<body>
<h1>Telegent Web Panel</h1>
<p>API aktif di <code>/api</code>. Build frontend untuk menyalakan antarmuka.</p>
</body>
</html>
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Siapkan dan tutup resource web selama aplikasi hidup."""
    cfg = cast(BootstrapConfig, app.state.bootstrap)
    cfg.ensure_data_dir()

    # Migrasi jalan di thread terpisah: Alembic (driver async) memakai
    # asyncio.run() yang tidak boleh dipanggil dari loop yang sedang aktif.
    await upgrade_to_head_async(cfg.db_url)
    db = Database(cfg.db_url)
    cipher = SecretCipher.from_bootstrap(cfg)
    store = SettingsStore(db, cipher)
    await store.import_env_once()

    app.state.db = db
    app.state.cipher = cipher
    app.state.settings_store = store

    configured = "siap" if await store.is_configured() else "belum lengkap"
    log.info(
        "Web panel siap (data=%s, db=%s, konfigurasi=%s, frontend=%s).",
        cfg.data_dir,
        cfg.db_url,
        configured,
        cfg.frontend_dist if cfg.has_frontend else "(belum dibangun)",
    )
    try:
        yield
    finally:
        # Runtime controller (A7) akan menutup diri sebelum database.
        app.state.settings_store = None
        await db.dispose()
        app.state.db = None
        log.info("Web panel berhenti.")


def _add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def _security_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


def _is_api_path(full_path: str) -> bool:
    return full_path == "api" or full_path.startswith("api/")


def _resolve_static(dist: Path, full_path: str) -> Path | None:
    """Cari berkas statis di dalam dist; None bila hilang atau keluar dari dist."""
    candidate = (dist / full_path).resolve()
    try:
        candidate.relative_to(dist.resolve())
    except ValueError:
        return None  # mencoba keluar dari direktori dist
    return candidate if candidate.is_file() else None


def _mount_frontend(app: FastAPI, cfg: BootstrapConfig) -> None:
    """Layani SPA: aset statis, fallback routing, dan halaman placeholder."""
    dist = cfg.frontend_dist
    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        if _is_api_path(full_path):
            return JSONResponse(
                {"error": {"code": "not_found", "message": "Endpoint tidak ditemukan."}},
                status_code=404,
            )

        if full_path:
            existing = _resolve_static(dist, full_path)
            if existing is not None:
                return FileResponse(existing)
            # Permintaan berkas (mem ekstensi) yang hilang: 404, bukan fallback SPA.
            if "." in Path(full_path).name:
                return JSONResponse(
                    {"error": {"code": "not_found", "message": "Berkas tidak ditemukan."}},
                    status_code=404,
                )

        if index_file.is_file():
            return FileResponse(index_file)
        return HTMLResponse(_PLACEHOLDER_HTML)


def create_app(config: BootstrapConfig | None = None) -> FastAPI:
    """Buat aplikasi web panel.

    Argumen `config` dipakai pengujian untuk mengisolasi direktori data & database.
    """
    cfg = config if config is not None else load_bootstrap()

    app = FastAPI(
        title="Telegent Web Panel",
        version=__version__,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.state.bootstrap = cfg
    # Runnable diisi pada tiket A2 (database), A7 (runtime) dan A8 (event bus).
    app.state.db = None
    app.state.events = None
    app.state.runtime = None

    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)

    _add_security_headers(app)
    _mount_frontend(app, cfg)
    return app