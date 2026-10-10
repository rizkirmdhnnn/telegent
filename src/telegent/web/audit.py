"""Audit log: jejak perubahan konfigurasi & aksi administratif.

Nilai secret selalu disamarkan sebelum ditulis, sehingga isi `audit_log` aman
untuk ditampilkan di UI maupun dibaca saat pemecahan masalah.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from telegent.web.crypto import mask
from telegent.web.db import models
from telegent.web.db.base import Database
from telegent.web.settings_registry import REGISTRY

log = logging.getLogger("telegent.web.audit")

SYSTEM_ACTOR = "system"
_MAX_DEPTH = 6

#: Petunjuk nama kolom yang selalu dianggap secret.
_SECRET_HINTS = (
    "password",
    "api_hash",
    "api_key",
    "secret",
    "token",
    "csrf",
    "code",
)


def is_secret_key(key: str) -> bool:
    """True bila nilai dengan nama ini tidak boleh disimpan apa adanya."""
    spec = REGISTRY.get(key)
    if spec is not None and spec.secret:
        return True
    lowered = key.lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def sanitize(value: Any, *, depth: int = 0) -> Any:
    """Salin struktur dengan nilai di bawah kunci secret disamarkan (rekursif)."""
    if depth > _MAX_DEPTH:
        return "…"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if is_secret_key(str(key)) and item is not None:
                result[str(key)] = mask(str(item))
            else:
                result[str(key)] = sanitize(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth=depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


@dataclass
class AuditEntry:
    """Satu perubahan yang perlu dicatat."""

    action: str
    actor: str = SYSTEM_ACTOR
    target: str | None = None
    before: Any = None
    after: Any = None
    ip: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _dump(value: Any, *, secret: bool) -> str | None:
    """Serialisasi aman untuk disimpan (secret disamarkan)."""
    if value is None:
        return None
    if secret:
        return json.dumps(mask(str(value)), ensure_ascii=False)
    return json.dumps(sanitize(value), ensure_ascii=False, default=str)


def _to_model(entry: AuditEntry) -> models.AuditLog:
    secret = is_secret_key(entry.target or "")
    return models.AuditLog(
        actor=entry.actor,
        action=entry.action,
        target=entry.target,
        before_json=_dump(entry.before, secret=secret),
        after_json=_dump(entry.after, secret=secret),
        ip=entry.ip,
    )


async def record_audit(db: Database, entry: AuditEntry) -> None:
    """Tulis satu entri audit (kegagalan tidak boleh menggagalkan aksi utama)."""
    try:
        async with db.session() as session:
            session.add(_to_model(entry))
    except Exception:  # noqa: BLE001
        log.exception("Gagal menulis entri audit '%s'.", entry.action)


async def record_many(db: Database, entries: list[AuditEntry]) -> None:
    """Tulis beberapa entri dalam satu transaksi."""
    if not entries:
        return
    async with db.session() as session:
        for entry in entries:
            session.add(_to_model(entry))