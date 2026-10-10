"""Unit test pembatas laju panggilan per pengguna."""

from __future__ import annotations

from telegent.rate_limit import CallRateLimiter


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_menonaktifkan_bila_batas_nol():
    limiter = CallRateLimiter(0, 60.0)
    for _ in range(100):
        assert limiter.allow(1) is True


def test_membatasi_jumlah_panggilan_dalam_jendela():
    clock = _FakeClock()
    limiter = CallRateLimiter(3, 60.0, clock=clock)

    assert [limiter.allow(1) for _ in range(4)] == [True, True, True, False]
    # Pengguna lain tidak terpengaruh.
    assert limiter.allow(2) is True


def test_jendela_bergulir_membuka_kembali():
    clock = _FakeClock()
    limiter = CallRateLimiter(2, 60.0, clock=clock)

    assert limiter.allow(1) is True
    assert limiter.allow(1) is True
    assert limiter.allow(1) is False

    # Belum lewat jendela -> masih ditolak.
    clock.advance(30.0)
    assert limiter.allow(1) is False

    # Lewat jendela -> diizinkan lagi.
    clock.advance(31.0)
    assert limiter.allow(1) is True


def test_reset_menghapus_riwayat():
    clock = _FakeClock()
    limiter = CallRateLimiter(1, 60.0, clock=clock)
    assert limiter.allow(1) is True
    assert limiter.allow(1) is False
    limiter.reset(1)
    assert limiter.allow(1) is True
