"""Router API web panel."""

from __future__ import annotations

from telegent.web.routers import health

#: Router yang sudah siap dipasang; bertambah pada tiket-tiket berikutnya.
ROUTERS = [health.router]

__all__ = ["ROUTERS", "health"]