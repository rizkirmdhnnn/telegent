"""Skema data untuk endpoint pengaturan (spesifikasi §6.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingItem(BaseModel):
    """Satu item pengaturan yang disajikan ke antarmuka web."""

    key: str
    type: str
    apply: str
    secret: bool
    advanced: bool
    is_set: bool
    value: Any = None


class SettingGroup(BaseModel):
    """Kelompok pengaturan."""

    group: str
    items: list[SettingItem]


class SettingsListResponse(BaseModel):
    """Respons untuk `GET /api/settings`."""

    groups: list[SettingGroup]
    pending_restart: bool = False
    pending_restart_keys: list[str] = Field(default_factory=list)


class UpdateSettingsRequest(BaseModel):
    """Permintaan untuk `PUT /api/settings`."""

    changes: dict[str, Any] = Field(default_factory=dict)


class UpdateSettingsResponse(BaseModel):
    """Hasil pembaruan pengaturan."""

    applied: list[str] = Field(default_factory=list)
    needs_restart: list[str] = Field(default_factory=list)
