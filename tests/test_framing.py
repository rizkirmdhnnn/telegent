"""Unit test framing PCM."""

from __future__ import annotations

from telegent.audio.framing import PcmFramer


def test_framer_splits_and_keeps_remainder():
    framer = PcmFramer(4)
    assert framer.push(b"aa") == []
    assert framer.pending == 2
    assert framer.push(b"bbccdd") == [b"aabb", b"ccdd"]
    assert framer.pending == 0
    assert framer.push(b"ee") == []
    assert framer.pending == 2


def test_framer_clear():
    framer = PcmFramer(4)
    framer.push(b"abcd")
    framer.clear()
    assert framer.pending == 0
