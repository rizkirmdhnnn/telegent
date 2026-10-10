"""Penyimpanan konfigurasi tool (tabel `tool_config`).

Pemisahan ini menjaga router tetap tipis dan memungkinkan `RuntimeController`
memuat konfigurasi yang sama saat membangun bot.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from telegent.web.db import models
from telegent.web.db.base import Database

log = logging.getLogger("telegent.web.tools_store")


@dataclass(frozen=True)
class ToolSetting:
    """Status aktif + parameter satu tool."""

    name: str
    enabled: bool
    config: dict[str, Any] | None


def _parse(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Konfigurasi tool JSON rusak; diabaikan.")
        return None
    return parsed if isinstance(parsed, dict) else None


async def load_tool_settings(db: Database) -> dict[str, ToolSetting]:
    """Seluruh konfigurasi tool tersimpan, diindeks berdasarkan nama."""
    async with db.session() as session:
        rows = (await session.execute(select(models.ToolConfig))).scalars().all()
    return {
        row.name: ToolSetting(
            name=row.name, enabled=row.enabled, config=_parse(row.config_json)
        )
        for row in rows
    }


async def tool_configs_for_runtime(db: Database) -> dict[str, dict[str, Any]]:
    """Kentuk `{nama: config}` untuk hidrasi `ToolRegistry`."""
    return {
        name: setting.config
        for name, setting in (await load_tool_settings(db)).items()
        if setting.config
    }


async def save_tool_setting(
    db: Database,
    name: str,
    *,
    enabled: bool | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[ToolSetting, ToolSetting]:
    """Simpan perubahan; kembalikan `(sebelum, sesudah)` untuk keperluan audit."""
    async with db.session() as session:
        row = await session.get(models.ToolConfig, name)
        before = ToolSetting(
            name=name,
            enabled=row.enabled if row else True,
            config=_parse(row.config_json) if row else None,
        )

        new_enabled = enabled if enabled is not None else before.enabled
        if config is not None:
            new_config = json.dumps(config, ensure_ascii=False)
        elif row is not None:
            new_config = row.config_json
        else:
            new_config = None

        if row is None:
            session.add(
                models.ToolConfig(name=name, enabled=new_enabled, config_json=new_config)
            )
        else:
            row.enabled = new_enabled
            row.config_json = new_config

    return before, ToolSetting(
        name=name,
        enabled=new_enabled,
        config=_parse(new_config),
    )