"""Router API web panel."""

from __future__ import annotations

from telegent.web.routers import (
    audit,
    auth,
    credentials,
    health,
    runtime,
    settings,
    setup,
    tools,
)

#: Router yang sudah siap dipasang; bertambah pada tiket-tiket berikutnya.
ROUTERS = [
    health.router,
    setup.router,
    auth.router,
    audit.router,
    settings.router,
    credentials.router,
    tools.router,
    runtime.router,
]

__all__ = [
    "ROUTERS",
    "audit",
    "auth",
    "credentials",
    "health",
    "runtime",
    "settings",
    "setup",
    "tools",
]