"""Skema data untuk endpoint kredensial (spesifikasi §6.3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from telegent.web.schemas.base import SimpleOkResponse


class TelegramCredentialsRequest(BaseModel):
    """Permintaan simpan kredensial Telegram.

    Field opsional: yang dikosongkan berarti "pertahankan yang tersimpan" —
    server memang tidak pernah mengirim nilai secret apa adanya ke UI.
    """

    api_id: int | None = Field(default=None, gt=0, description="Telegram App API ID")
    api_hash: str | None = Field(
        default=None,
        min_length=32,
        max_length=32,
        description="Telegram App API Hash (32 karakter hex)",
    )


class GeminiCredentialsRequest(BaseModel):
    """Permintaan simpan Gemini API key (opsional = pertahankan yang tersimpan)."""

    api_key: str | None = Field(
        default=None,
        min_length=20,
        max_length=200,
        description="Google Gemini API Key",
    )


class ValidateCredentialsRequest(BaseModel):
    """Permintaan validasi kredensial."""

    kind: Literal["telegram", "gemini"]


class ValidateCredentialsResponse(BaseModel):
    """Hasil validasi kredensial."""

    valid: bool
    code: str
    message: str
