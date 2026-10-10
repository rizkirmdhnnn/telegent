"""Endpoint pembacaan audit log."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from telegent.web.db import models
from telegent.web.deps import AdminDep, DatabaseDep

router = APIRouter(tags=["audit"])


def _decode(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


@router.get("/audit")
async def list_audit(
    admin: AdminDep,
    db: DatabaseDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    action: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """Daftar entri audit terbaru (terlama dulu)."""
    count_stmt = select(func.count()).select_from(models.AuditLog)
    stmt = select(models.AuditLog)

    if action:
        count_stmt = count_stmt.where(models.AuditLog.action == action)
        stmt = stmt.where(models.AuditLog.action == action)

    async with db.session() as session:
        total_value = (await session.execute(count_stmt)).scalar_one()
        rows = (
            await session.execute(
                stmt.order_by(models.AuditLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

    items = [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "target": row.target,
            "before": _decode(row.before_json),
            "after": _decode(row.after_json),
            "ip": row.ip,
            "at": row.at.isoformat() + "Z",
        }
        for row in rows
    ]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": int(total_value),
    }


@router.get("/audit/actions")
async def list_actions(admin: AdminDep, db: DatabaseDep) -> dict[str, list[str]]:
    """Daftar aksi yang pernah tercatat (untuk filter UI)."""
    async with db.session() as session:
        rows = (await session.execute(select(models.AuditLog.action).distinct())).scalars().all()
    return {"actions": sorted(rows)}