"""Format galat API yang konsisten (`{"error": {...}}`) beserta handler-nya."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from telegent.web.settings_registry import SettingsValidationError


class APIError(Exception):
    """Galat aplikasi yang dikembalikan sebagai JSON terstruktur."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields

    def payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code}
        if self.message:
            error["message"] = self.message
        if self.fields:
            error["fields"] = self.fields
        return {"error": error}


def _json(status_code: int, payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload)


def install_error_handlers(app: FastAPI) -> None:
    """Pasang handler galat agar seluruh respons memakai format yang sama."""

    @app.exception_handler(APIError)
    async def _handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
        del _request
        return _json(exc.status_code, exc.payload())

    @app.exception_handler(SettingsValidationError)
    async def _handle_settings_validation_error(
        _request: Request, exc: SettingsValidationError
    ) -> JSONResponse:
        del _request
        return _json(
            422,
            {
                "error": {
                    "code": "validation_error",
                    "message": "Pengaturan tidak valid.",
                    "fields": exc.as_dict(),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del _request
        fields = {}
        for item in exc.errors():
            location = [str(part) for part in item.get("loc", []) if part != "body"]
            fields[".".join(location) or "body"] = {"code": str(item.get("type", "invalid"))}
        return _json(
            422,
            {
                "error": {
                    "code": "validation_error",
                    "message": "Permintaan tidak valid.",
                    "fields": fields,
                }
            },
        )