"""Skema data untuk endpoint tools (spesifikasi §6.7)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolItemResponse(BaseModel):
    """Informasi satu tool."""

    name: str
    description: str
    enabled: bool = True
    can_disable: bool = True
    config: dict[str, Any] | None = None
    parameters_json_schema: dict[str, Any] = Field(default_factory=dict)
    timeout: float = 5.0
    behavior: str = "BLOCKING"


class UpdateToolRequest(BaseModel):
    """Permintaan konfigurasi tool."""

    enabled: bool | None = None
    config: dict[str, Any] | None = None
