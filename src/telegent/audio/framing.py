"""Pemecahan aliran PCM menjadi frame berukuran tetap."""

from __future__ import annotations


class PcmFramer:
    """Buffering + pemecahan PCM s16le mono menjadi frame berukuran tepat.

    Sisa byte yang belum cukup satu frame disimpan untuk pemanggilan berikutnya,
    sehingga tidak ada celah/sampel yang hilang di antara potongan.
    """

    def __init__(self, frame_bytes: int) -> None:
        if frame_bytes <= 0:
            raise ValueError("frame_bytes harus > 0")
        self.frame_bytes = frame_bytes
        self._buffer = bytearray()

    def push(self, pcm: bytes) -> list[bytes]:
        self._buffer.extend(pcm)
        frames: list[bytes] = []
        n = self.frame_bytes
        while len(self._buffer) >= n:
            frames.append(bytes(self._buffer[:n]))
            del self._buffer[:n]
        return frames

    def clear(self) -> None:
        self._buffer.clear()

    @property
    def pending(self) -> int:
        return len(self._buffer)
