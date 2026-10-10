"""Router API web panel."""

from __future__ import annotations

from telegent.web.routers import audit, auth, health, setup

#: Router yang sudah siap dipasang; bertambah pada tiket-tiket berikutnya.
ROUTERS = [health.router, setup.router, auth.router, audit.router]

__all__ = ["ROUTERS", "audit", "auth", "health", "setup"]