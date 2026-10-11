"""Test mode fake `telegent.web.fake` (tiket G1/H3).

Yang paling penting di berkas ini adalah **gerbang keamanannya**: mode fake
adalah pengganti runtime produksi, jadi tidak boleh bisa menyala karena salah
ketik env atau karena variabel yang tersesat ke `.env`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pyrogram.errors import BadRequest

from telegent.config import Settings
from telegent.web import fake
from telegent.web.bootstrap import load_bootstrap


@pytest.fixture(autouse=True)
def _clear_fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGENT_FAKE", raising=False)
    monkeypatch.delenv("TELEGENT_FAKE_CALL_INTERVAL", raising=False)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        telegram_api_id=1,
        telegram_api_hash="h",
        gemini_api_key="k",
        session_dir=str(tmp_path),
        _env_file=None,  # type: ignore[call-arg]
    )


# ------------------------------------------------------------- gerbang env


def test_hanya_nilai_1_yang_mengaktifkan() -> None:
    """`TELEGENT_FAKE=1` adalah satu-satunya nilai yang sah."""
    assert fake.fake_enabled() is False  # tidak diset sama sekali


@pytest.mark.parametrize("value", ["1"])
def test_nilai_yang_mengaktifkan(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("TELEGENT_FAKE", value)
    assert fake.fake_enabled() is True


@pytest.mark.parametrize(
    "value",
    ["true", "TRUE", "yes", "on", "0", "false", "", "  ", "11", "1 1", "fake"],
)
def test_nilai_lain_tidak_mengaktifkan(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Salah ketik tidak boleh diam-diam mengganti produksi dengan mode tiruan."""
    monkeypatch.setenv("TELEGENT_FAKE", value)
    assert fake.fake_enabled() is False


def test_spasi_di_sekeliling_tetap_dihormati(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGENT_FAKE", "  1  ")
    assert fake.fake_enabled() is True


def test_env_tidak_aktif_maka_tanpa_peringatan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fake.warn_if_fake_enabled() is False
    assert "MODE FAKE" not in capsys.readouterr().err


def test_aktif_maka_peringatan_mencolok(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TELEGENT_FAKE", "1")
    assert fake.warn_if_fake_enabled() is True
    err = capsys.readouterr().err
    assert "MODE FAKE AKTIF" in err
    assert "produksi" in err


def test_dotenv_tidak_pernah_mengaktifkan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresi keamanan: `TELEGENT_FAKE` di `.env` harus DIABAIKAN.

    `load_bootstrap()` membaca flag sebelum `load_dotenv`, jadi file `.env`
    tidak bisa menyalakan mode tiruan produksi.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TELEGENT_FAKE=1\n", encoding="utf-8")
    monkeypatch.delenv("TELEGENT_FAKE", raising=False)

    cfg = load_bootstrap(data_dir=tmp_path / "data")

    assert cfg.fake is False


def test_env_proses_mengaktifkan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGENT_FAKE", "1")
    cfg = load_bootstrap(data_dir=tmp_path / "data")
    assert cfg.fake is True


# ------------------------------------------------------- interval panggilan


def test_interval_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGENT_FAKE_CALL_INTERVAL", raising=False)
    assert fake.fake_call_interval() == fake.DEFAULT_CALL_INTERVAL_SEC


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("3", 3.0), ("0.5", 0.5), ("abc", fake.DEFAULT_CALL_INTERVAL_SEC), ("-1", fake.DEFAULT_CALL_INTERVAL_SEC)],
)
def test_interval_diparse(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
) -> None:
    monkeypatch.setenv("TELEGENT_FAKE_CALL_INTERVAL", raw)
    assert fake.fake_call_interval() == expected


def test_mask_phone_menyembunyikan_sebagian() -> None:
    assert fake.mask_phone("+6281234567890") == "***7890"
    # Nomor pendek disamarkan penuh: menyisakan 4 digit terakhir tidak menambah
    # keamanan, hanya membocorkan lebih banyak.
    assert fake.mask_phone("12") == "**"


# ------------------------------------------------------------ klien Telegram


def test_klien_tiruan_menulis_berkas_sesi(tmp_path: Path) -> None:
    """Pyrogram menulis `*.session` saat start; tiruan harus sama."""
    credentials = fake.SimpleNamespace(session_name="userbot_session", api_id=1, api_hash="h")
    client = fake.FakeTelegramClient(credentials, tmp_path)

    asyncio.run(client.start())

    assert (tmp_path / "userbot_session.session").is_file()


def test_kode_otp_yang_diterima(tmp_path: Path) -> None:
    credentials = fake.SimpleNamespace(session_name="s", api_id=1, api_hash="h")
    client = fake.FakeTelegramClient(credentials, tmp_path)

    me = asyncio.run(client.sign_in("+6281234567890", fake.FAKE_LOGIN_CODE))

    assert me.id == fake.FAKE_TG_ID


def test_kode_otp_lain_ditolak(tmp_path: Path) -> None:
    """Kode salah harus jadi `BadRequest` — sama seperti Pyrogram aslinya."""
    credentials = fake.SimpleNamespace(session_name="s", api_id=1, api_hash="h")
    client = fake.FakeTelegramClient(credentials, tmp_path)

    with pytest.raises(BadRequest):
        asyncio.run(client.sign_in("+6281234567890", "00000"))


def test_kode_hash_tidak_membocorkan_nomor(tmp_path: Path) -> None:
    """`phone_code_hash` tidak boleh memuat nomor telepon mentah."""
    credentials = fake.SimpleNamespace(session_name="s", api_id=1, api_hash="h")
    client = fake.FakeTelegramClient(credentials, tmp_path)

    sent = asyncio.run(client.send_code("+6281234567890"))

    assert "6281234567890" not in str(sent.phone_code_hash)


def test_pabrik_klien_tiruan_kompatibel_dengan_layanan_login(tmp_path: Path) -> None:
    credentials = fake.SimpleNamespace(session_name="s", api_id=1, api_hash="h")
    client = fake.fake_client_factory(credentials, tmp_path)
    assert isinstance(client, fake.FakeTelegramClient)


# ------------------------------------------------------------------ bot tiruan


def test_bot_tiruan_tidak_membuat_klien_native(tmp_path: Path) -> None:
    """Tidak ada Pyrogram/ntgcalls/Gemini yang dibuat (pemicu error jaringan)."""
    app = fake.FakeTelegentApp(_settings(tmp_path))

    assert app.app is None
    assert app.ntg is None
    assert app.gemini_client is None
    assert app.is_running is False


def test_bot_tiruan_menjalankan_siklus_hidup(tmp_path: Path) -> None:
    app = fake.FakeTelegentApp(_settings(tmp_path))

    async def scenario() -> dict[str, Any]:
        await app.start()
        assert app.is_running is True
        assert app.active_sessions() == []
        payload = app.status_payload()
        await app.stop()
        await app.wait_stopped()
        return payload

    payload = asyncio.run(scenario())
    assert payload["running"] is True
    assert payload["logged_in_user"]["username"] == fake.FAKE_TG_USERNAME

    asyncio.run(app.shutdown())
    assert app.is_running is False


def test_bot_tiruan_menerbitkan_rangkaian_panggilan(tmp_path: Path) -> None:
    """Satu panggilan tiruan harus melewati observer lengkap: incoming → end."""
    seen: list[tuple[str, int]] = []

    class _Observer:
        def call_incoming(self, tg_call_id: int, user_id: int, **kw: Any) -> None:
            seen.append(("incoming", tg_call_id))

        def call_started(self, tg_call_id: int, user_id: int) -> None:
            seen.append(("started", tg_call_id))

        def call_ended(self, tg_call_id: int, user_id: int, **kw: Any) -> None:
            seen.append(("ended", tg_call_id))

        def session_event(self, tg_call_id: int, event: str, data: dict) -> None:
            seen.append((event, tg_call_id))

    app = fake.FakeTelegentApp(_settings(tmp_path), call_observer=_Observer())

    app._simulate_call()

    kinds = [kind for kind, _ in seen]
    assert kinds == ["incoming", "started", "transcript", "transcript", "tool_call", "ended"]


def test_pabrik_app_tiruan_signature_cocok(tmp_path: Path) -> None:
    factory = fake.fake_app_factory(event_sink=None, call_observer=None)
    built = factory(_settings(tmp_path))
    assert isinstance(built, fake.FakeTelegentApp)


def test_bot_tiruan_terhentikan_otomatis(tmp_path: Path) -> None:
    """Task pengactoryuan panggilan harus berhenti saat bot dihentikan."""
    monkey_interval = 0.05
    app = fake.FakeTelegentApp(_settings(tmp_path))

    async def scenario() -> None:
        await app.start()
        await asyncio.sleep(monkey_interval)
        await app.stop()
        await app.wait_stopped()
        await app.shutdown()

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))