"""Dependency bersama untuk router web panel."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from telegent.web.bootstrap import BootstrapConfig


def get_bootstrap(request: Request) -> BootstrapConfig:
    """Konfigurasi bootstrap yang dipasang `create_app` saat startup."""
    return cast(BootstrapConfig, request.app.state.bootstrap)