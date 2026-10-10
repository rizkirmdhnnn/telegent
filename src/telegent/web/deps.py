"""Dependency bersama untuk router web panel."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from telegent.web.bootstrap import BootstrapConfig
from telegent.web.crypto import SecretCipher
from telegent.web.db.base import Database
from telegent.web.errors import APIError
from telegent.web.security import CSRF_COOKIE, SESSION_COOKIE, AdminSession, SessionManager
from telegent.web.settings_store import SettingsStore


def get_bootstrap(request: Request) -> BootstrapConfig:
    """Konfigurasi bootstrap yang dipasang `create_app` saat startup."""
    return cast(BootstrapConfig, request.app.state.bootstrap)


def get_sessions(request: Request) -> SessionManager:
    return cast(SessionManager, request.app.state.sessions)


def get_database(request: Request) -> Database:
    db = request.app.state.db
    if db is None:
        raise APIError(503, "database_unavailable", "Database belum siap.")
    return cast(Database, db)


def get_settings_store(request: Request) -> SettingsStore:
    store = request.app.state.settings_store
    if store is None:
        raise APIError(503, "store_unavailable", "Store konfigurasi belum siap.")
    return cast(SettingsStore, store)


def get_cipher(request: Request) -> SecretCipher:
    cipher = request.app.state.cipher
    if cipher is None:
        raise APIError(503, "store_unavailable", "Penyimpan secret belum siap.")
    return cast(SecretCipher, cipher)


def current_session(request: Request) -> AdminSession | None:
    session = get_sessions(request).get(request.cookies.get(SESSION_COOKIE))
    return session


def require_admin(request: Request) -> AdminSession:
    """Sesi admin yang sah; 401 bila tidak."""
    session = current_session(request)
    if session is None:
        raise APIError(401, "unauthenticated", "Silakan masuk terlebih dahulu.")
    return session


def require_csrf(request: Request) -> AdminSession:
    """Sesi admin + token CSRF valid (double submit cookie)."""
    session = require_admin(request)
    header = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or header != cookie or header != session.csrf_token:
        raise APIError(403, "csrf_failed", "Token CSRF tidak valid.")
    return session


BootstrapDep = Annotated[BootstrapConfig, Depends(get_bootstrap)]
SessionsDep = Annotated[SessionManager, Depends(get_sessions)]
DatabaseDep = Annotated[Database, Depends(get_database)]
StoreDep = Annotated[SettingsStore, Depends(get_settings_store)]
CipherDep = Annotated[SecretCipher, Depends(get_cipher)]
AdminDep = Annotated[AdminSession, Depends(require_admin)]
CsrfDep = Annotated[AdminSession, Depends(require_csrf)]