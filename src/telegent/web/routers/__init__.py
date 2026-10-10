"""Router API web panel."""

from __future__ import annotations

from telegent.web.routers import (
    audit,
    auth,
    calls,
    credentials,
    events,
    health,
    runtime,
    settings,
    setup,
    telegram,
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
    telegram.router,
    runtime.router,
    calls.router,
    events.router,
]

__all__ = [
    "ROUTERS",
    "audit",
    "auth",
    "calls",
    "credentials",
    "events",
    "health",
    "runtime",
    "settings",
    "setup",
    "telegram",
    "tools",
]