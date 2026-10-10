"""Pembatas laju panggilan masuk (per pengguna) untuk mencegah penyalahgunaan.

Setiap panggilan masuk dihitung sebagai satu percobaan, terlepas dari apakah
akhirnya diterima atau ditolak karena kapasitas. Ini mencegah penelpon yang sama
menghujani server dengan panggilan beruntun (yang memicu biaya Gemini).

Semua state bersifat per-instance dan hanya disentuh dari event loop utama.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Deque, Dict

# Clock default memakai monotonic agar tidak terpengaruh perubahan jam sistem.
Clock = Callable[[], float]


class CallRateLimiter:
    """Membatasi jumlah panggilan per pengguna dalam jendela waktu bergulir.

    ``max_calls <= 0`` menonaktifkan pembatasan (selalu mengizinkan).
    """

    def __init__(
        self,
        max_calls: int,
        window_seconds: float,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._clock = clock
        self._events: Dict[int, Deque[float]] = {}

    def allow(self, user_id: int) -> bool:
        """Catat percobaan panggilan; kembalikan False bila melewati batas."""
        if self._max <= 0:
            return True

        now = self._clock()
        events = self._events.setdefault(user_id, deque())
        cutoff = now - self._window
        while events and events[0] <= cutoff:
            events.popleft()

        if len(events) >= self._max:
            return False

        events.append(now)
        return True

    def reset(self, user_id: int) -> None:
        """Bersihkan riwayat satu pengguna (mis. saat pengujian)."""
        self._events.pop(user_id, None)
