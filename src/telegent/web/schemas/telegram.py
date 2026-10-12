"""Skema data untuk endpoint akun & login Telegram (spesifikasi §6.4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from telegent.web.schemas.base import SimpleOkResponse

#: Langkah setelah `login/start` (hanya kode yang dipakai; `password` disediakan
#: agar kontrak tidak berubah bila alur(authorisasi) berkembang).
LoginNext = Literal["code", "password", "done"]


class LoginStartRequest(BaseModel):
    """Mulai alur login; nomor telepon dalam format internasional."""

    phone: str = Field(
        min_length=6,
        max_length=32,
        description="Nomor telepon internasional, mis. +6281234567890",
    )


class LoginVerifyRequest(BaseModel):
    """Kirim kode OTP yang diterima dari Telegram."""

    flow_id: int = Field(gt=0, description="Id alur login dari `login/start`")
    code: str = Field(min_length=1, max_length=16, description="Kode OTP dari Telegram")


class LoginPasswordRequest(BaseModel):
    """Kirim password 2FA (hanya bila akun memakai two-step verification)."""

    flow_id: int = Field(gt=0, description="Id alur login dari `login/verify`")
    password: str = Field(min_length=1, max_length=128, description="Password 2FA")


class LoginCancelRequest(BaseModel):
    """Batalkan alur login yang belum selesai."""

    flow_id: int = Field(gt=0, description="Id alur login yang dibatalkan")


class LoginStartResponse(BaseModel):
    """Respons `login/start`."""

    flow_id: int
    next: LoginNext = "code"


class LoginVerifyResponse(BaseModel):
    """Respons `login/verify`: langkah berikutnya (`password` atau `done`)."""

    next: LoginNext
