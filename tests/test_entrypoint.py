"""Unit test entry point (khususnya jalur keluar bersih)."""

from __future__ import annotations

import telegent.__main__ as entry


def test_exit_cleanly_memakai_os_exit(monkeypatch):
    """Harus keluar via os._exit agar destruktor statis ntgcalls tidak jalan."""
    captured = {}
    monkeypatch.setattr(entry.os, "_exit", lambda code: captured.setdefault("code", code))

    entry._exit_cleanly(7)

    assert captured["code"] == 7
