"""Skema request/response untuk autentikasi & setup."""

from __future__ import annotations

from pydantic import BaseModel, Field

from telegent.web.schemas.base import SimpleOkResponse


class SetupStatus(BaseModel):
    needs_setup: bool


class CreateAdminRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, max_length=16)


#: Bentuk sama dengan `SimpleOkResponse`; dipakai sebagai alias agar endpoint
#: auth punya nama domain yang jelas.
MessageResponse = SimpleOkResponse


class MeResponse(BaseModel):
    username: str
    totp_enabled: bool
    locale: str
    theme: str


class UpdateMeRequest(BaseModel):
    locale: str | None = Field(default=None, max_length=8)
    theme: str | None = Field(default=None, max_length=16)


class ChangePasswordRequest(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg: str


class TotpCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16)