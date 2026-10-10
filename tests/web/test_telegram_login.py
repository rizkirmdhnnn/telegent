"""Test `TelegramLoginService` (tiket D1).

Pyrogram di-*stub* sepenuhnya — tidak ada jaringan yang tersentuh. Skema
skenario digerakkan lewat `FakeTelegram`, sehingga alur sukses, 2FA, FloodWait,
dan setiap pemetaan galat dapat diuji tanpa akun Telegram sungguhan.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pyrogram.errors import (
    FloodWait,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)

from telegent.web.db import models
from telegent.web.db.base import Database, utcnow
from telegent.web.events import EventBus
from telegent.web.log_stream import BusLogHandler, LogRingBuffer, SecretRedactor
from telegent.web.settings_store import SettingsStore
from telegent.web.telegram_login import (
    ACCOUNT_LOGGED_IN,
    ACCOUNT_NOT_CONFIGURED,
    FLOW_AWAITING_PASSWORD,
    FLOW_CODE_SENT,
    TelegramLoginError,
    TelegramLoginService,
    map_exception,
    normalize_phone,
)

_API_ID = 12345678
_API_HASH = "0123456789abcdef0123456789abcdef"
_PHONE = "+6281234567890"
_CODE = "54321"
_WRONG_CODE = "987654"
_2FA_PASSWORD = "rahasia-super-2fa"

#: Nilai sensitif yang tidak boleh muncul di log mana pun.
SECRET_CODE_HASH = "hash-rahasia-yang-panjang-sekali"


# ------------------------------------------------------------------ fake pyrogram


class FakeTelegram:
    """Pabrik klien Pyrogram palsu yang digerakkan skenario per nomor telepon."""

    #: Skenario aktif: `sign_in_error` / `password_error` yang harus dilempar.
    sign_in_error: BaseException | None = None
    password_error: BaseException | None = None
    send_code_error: BaseException | None = None
    me: Any = SimpleNamespace(id=5550001, username="telegent_bot", first_name="Telegent")
    instances: list["FakeClient"] = []

    @classmethod
    def reset(cls) -> None:
        cls.sign_in_error = None
        cls.password_error = None
        cls.send_code_error = None
        cls.instances.clear()

    @classmethod
    def factory(cls, name: str, api_id: int, api_hash: str, workdir: Path) -> "FakeClient":
        return FakeClient(name=name, api_id=api_id, api_hash=api_hash, workdir=workdir)


class FakeClient:
    """Klien Pyrogram minimal: hanya operasi yang dipakai layanan login."""

    def __init__(self, *, name: str, api_id: int, api_hash: str, workdir: Path) -> None:
        self.name = name
        self.api_id = api_id
        self.api_hash = api_hash
        self.workdir = workdir
        self.started = False
        self.stopped = False
        self.logged_out = False
        self.signed_in_with: tuple[str, str, str | None] | None = None
        self.checked_password: str | None = None
        # Pyrogram membuat berkas sesi begitu klien dijalankan.
        (workdir / f"{name}.session").write_bytes(b"fake-session")
        FakeTelegram.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_code(self, phone: str) -> Any:
        if FakeTelegram.send_code_error is not None:
            raise FakeTelegram.send_code_error
        self.sent_to = phone
        return SimpleNamespace(phone_code_hash=SECRET_CODE_HASH)

    async def sign_in(self, phone: str, code: str, *, phone_code_hash: str | None = None) -> Any:
        self.signed_in_with = (phone, code, phone_code_hash)
        if FakeTelegram.sign_in_error is not None:
            raise FakeTelegram.sign_in_error
        return FakeTelegram.me

    async def check_password(self, password: str) -> Any:
        self.checked_password = password
        if FakeTelegram.password_error is not None:
            raise FakeTelegram.password_error
        return FakeTelegram.me

    async def get_me(self) -> Any:
        return FakeTelegram.me

    async def log_out(self) -> None:
        self.logged_out = True


@pytest.fixture(autouse=True)
def fake_telegram() -> Iterator[None]:
    """Reset skenario fake Pyrogram sebelum & sesudah setiap pengujian."""
    FakeTelegram.reset()
    yield
    FakeTelegram.reset()


# --------------------------------------------------------------------- fixtures


@pytest.fixture
async def service(
    database: Database,
    store: SettingsStore,
    tmp_path: Path,
) -> TelegramLoginService:
    """Layanan login dengan kredensial Telegram sudah terisi."""
    await store.update(
        {"telegram_api_id": _API_ID, "telegram_api_hash": _API_HASH},
        actor="test",
    )
    return TelegramLoginService(
        database,
        store,
        data_dir=tmp_path / "data",
        client_factory=FakeTelegram.factory,
    )


async def _account(database: Database) -> models.TelegramAccount | None:
    async with database.session() as session:
        return await session.get(models.TelegramAccount, 1)


async def _flows(database: Database) -> list[models.LoginFlow]:
    from sqlalchemy import select

    async with database.session() as session:
        rows = (await session.execute(select(models.LoginFlow))).scalars().all()
        return list(rows)


# ------------------------------------------------------------------ happy path


async def test_login_s_ukses_tanpa_2fa(
    service: TelegramLoginService, database: Database
) -> None:
    start = await service.start(_PHONE)
    assert start.next == "code"
    assert start.flow_id > 0

    flows = await _flows(database)
    assert len(flows) == 1
    assert flows[0].phone == _PHONE
    assert flows[0].status == FLOW_CODE_SENT
    assert flows[0].expires_at > utcnow()

    result = await service.verify(start.flow_id, _CODE)
    assert result.next == "done"

    account = await _account(database)
    assert account is not None
    assert account.status == ACCOUNT_LOGGED_IN
    assert account.tg_user_id == 5550001
    assert account.tg_username == "telegent_bot"
    assert account.tg_first_name == "Telegent"
    assert account.phone == _PHONE
    assert account.logged_in_at is not None
    assert account.last_error is None

    # Flow selesai langsung dibuang.
    assert await _flows(database) == []
    # Klien dilepas agar berkas sesi bisa dipakai runtime.
    assert FakeTelegram.instances[-1].stopped is True


async def test_status_menampilkan_akun_setelah_login(
    service: TelegramLoginService,
) -> None:
    start = await service.start(_PHONE)
    await service.verify(start.flow_id, _CODE)

    status = await service.status()
    assert status["status"] == ACCOUNT_LOGGED_IN
    assert status["phone"] == _PHONE
    assert status["user"] == {
        "id": 5550001,
        "username": "telegent_bot",
        "first_name": "Telegent",
    }
    assert status["credentials_configured"] is True
    assert status["session_mismatch"] is False
    assert status["last_error"] is None
    assert isinstance(status["logged_in_at"], str)


async def test_login_dengan_2fa(
    service: TelegramLoginService, database: Database
) -> None:
    FakeTelegram.sign_in_error = SessionPasswordNeeded()
    start = await service.start(_PHONE)

    result = await service.verify(start.flow_id, _CODE)
    assert result.next == "password"

    flows = await _flows(database)
    assert len(flows) == 1
    assert flows[0].status == FLOW_AWAITING_PASSWORD

    await service.submit_password(start.flow_id, _2FA_PASSWORD)

    account = await _account(database)
    assert account is not None
    assert account.status == ACCOUNT_LOGGED_IN
    assert account.tg_user_id == 5550001
    assert await _flows(database) == []
    assert FakeTelegram.instances[-1].checked_password == _2FA_PASSWORD


async def test_password_salah_menolak_tanpa_mengganti_status(
    service: TelegramLoginService, database: Database
) -> None:
    FakeTelegram.sign_in_error = SessionPasswordNeeded()
    start = await service.start(_PHONE)
    await service.verify(start.flow_id, _CODE)

    FakeTelegram.password_error = PasswordHashInvalid()
    with pytest.raises(TelegramLoginError) as excinfo:
        await service.submit_password(start.flow_id, "salah")
    assert excinfo.value.code == "password_invalid"

    # Flow tetap hidup supaya admin mencoba lagi.
    flows = await _flows(database)
    assert len(flows) == 1 and flows[0].status == FLOW_AWAITING_PASSWORD

    FakeTelegram.password_error = None
    await service.submit_password(start.flow_id, _2FA_PASSWORD)
    account = await _account(database)
    assert account is not None and account.status == ACCOUNT_LOGGED_IN


# --------------------------------------------------------------- pemetaan galat


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (PhoneNumberInvalid(), "phone_invalid"),
        (PhoneCodeInvalid(), "code_invalid"),
        (PhoneCodeExpired(), "code_expired"),
        (PasswordHashInvalid(), "password_invalid"),
        (FloodWait(value=42), "flood_wait"),
        (ConnectionError("jaringan mati"), "network_error"),
        (TimeoutError("timeout"), "network_error"),
        (RuntimeError("aneh"), "telegram_error"),
    ],
)
def test_map_exception_menghasilkan_kode_stabil(
    exception: BaseException, expected_code: str
) -> None:
    error = map_exception(exception)
    assert error.code == expected_code
    assert isinstance(error.message, str) and error.message


def test_flood_wait_membawa_retry_after() -> None:
    error = map_exception(FloodWait(value=137))
    assert error.code == "flood_wait"
    assert error.retry_after == 137
    assert error.status_code == 429
    assert error.fields() == {"retry_after": 137}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+62 812-3456-7890", "+6281234567890"),
        ("081234567890", "+081234567890"),
        ("  +6281234567890 ", "+6281234567890"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "+62", "12345", "+62" * 20])
def test_normalize_phone_menolak_tidak_valid(raw: str) -> None:
    with pytest.raises(TelegramLoginError) as excinfo:
        normalize_phone(raw)
    assert excinfo.value.code == "phone_invalid"


async def test_nomor_tidak_valid_ditolak_sebelum_jaringan(
    service: TelegramLoginService,
) -> None:
    with pytest.raises(TelegramLoginError) as excinfo:
        await service.start("bukan-nomor")
    assert excinfo.value.code == "phone_invalid"
    assert FakeTelegram.instances == []


async def test_kode_terlalu_panjang_ditolak(
    service: TelegramLoginService, database: Database
) -> None:
    start = await service.start(_PHONE)
    with pytest.raises(TelegramLoginError) as excinfo:
        await service.verify(start.flow_id, "abcdefghijk")
    assert excinfo.value.code == "code_invalid"
    # Alur tidak consumed: admin masih bisa mengetik kode yang benar.
    assert len(await _flows(database)) == 1


async def test_flood_wait_dari_send_code(
    service: TelegramLoginService, database: Database
) -> None:
    FakeTelegram.send_code_error = FloodWait(value=300)
    with pytest.raises(TelegramLoginError) as excinfo:
        await service.start(_PHONE)

    assert excinfo.value.code == "flood_wait"
    assert excinfo.value.retry_after == 300
    assert await _flows(database) == []
    account = await _account(database)
    assert account is not None and account.last_error == "flood_wait"


async def test_kode_salah_mencatat_last_error(
    service: TelegramLoginService, database: Database
) -> None:
    start = await service.start(_PHONE)
    FakeTelegram.sign_in_error = PhoneCodeInvalid()
    with pytest.raises(TelegramLoginError) as excinfo:
        await service.verify(start.flow_id, "00000")

    assert excinfo.value.code == "code_invalid"
    account = await _account(database)
    assert account is not None
    assert account.last_error == "code_invalid"
    assert account.status != ACCOUNT_LOGGED_IN


async def test_kredensial_belum_diisi_gagal_jelas(
    database: Database, store: SettingsStore, tmp_path: Path
) -> None:
    service = TelegramLoginService(
        database, store, data_dir=tmp_path / "data", client_factory=FakeTelegram.factory
    )
    status = await service.status()
    assert status["status"] == ACCOUNT_NOT_CONFIGURED
    assert status["credentials_configured"] is False

    with pytest.raises(TelegramLoginError) as excinfo:
        await service.start(_PHONE)
    assert excinfo.value.code == "api_credentials_missing"
    assert excinfo.value.status_code == 409


# ------------------------------------------------------------------- lifecycle


async def test_cancel_membuang_flow(
    service: TelegramLoginService, database: Database
) -> None:
    start = await service.start(_PHONE)
    client = FakeTelegram.instances[-1]

    await service.cancel(start.flow_id)

    assert await _flows(database) == []
    assert client.stopped is True

    with pytest.raises(TelegramLoginError) as excinfo:
        await service.cancel(start.flow_id)
    assert excinfo.value.code == "flow_not_found"


async def test_flow_baru_membatalkan_flow_lama(
    service: TelegramLoginService, database: Database
) -> None:
    first = await service.start(_PHONE)
    first_client = FakeTelegram.instances[-1]

    second = await service.start(_PHONE)

    assert first_client.stopped is True
    # Id flow tidak pernah dipakai ulang, jadi flow lama benar-benar hilang.
    assert second.flow_id != first.flow_id
    flows = await _flows(database)
    assert [flow.id for flow in flows] == [second.flow_id]

    with pytest.raises(TelegramLoginError) as excinfo:
        await service.verify(first.flow_id, _CODE)
    assert excinfo.value.code == "flow_not_found"


async def test_flow_kedaluwarsa_ditolak(
    service: TelegramLoginService, database: Database
) -> None:
    start = await service.start(_PHONE)
    async with database.session() as session:
        flow = await session.get(models.LoginFlow, start.flow_id)
        assert flow is not None
        flow.expires_at = utcnow() - timedelta(minutes=1)

    with pytest.raises(TelegramLoginError) as excinfo:
        await service.verify(start.flow_id, _CODE)
    assert excinfo.value.code == "flow_expired"
    assert excinfo.value.status_code == 410


async def test_cleanup_expired_membuang_flow_kedaluwarsa(
    service: TelegramLoginService, database: Database
) -> None:
    fresh = await service.start(_PHONE)
    async with database.session() as session:
        session.add(
            models.LoginFlow(
                phone=_PHONE,
                phone_code_hash=SECRET_CODE_HASH,
                status=FLOW_CODE_SENT,
                created_at=utcnow() - timedelta(minutes=30),
                expires_at=utcnow() - timedelta(minutes=20),
            )
        )

    removed = await service.cleanup_expired()

    assert removed == 1
    remaining = await _flows(database)
    assert [flow.id for flow in remaining] == [fresh.flow_id]


async def test_logout_menghapus_berkas_sesi(
    service: TelegramLoginService, database: Database, tmp_path: Path
) -> None:
    start = await service.start(_PHONE)
    await service.verify(start.flow_id, _CODE)
    session_file = service.session_path("userbot_session")
    assert session_file.is_file()
    # Berkas logamamping dari proses lain ikut dibersihkan.
    stray = service.session_path("userbot_session").with_suffix(".session-journal")
    stray.write_bytes(b"stray")

    result = await service.logout()

    assert result["removed_session_files"] >= 2
    assert result["remote_error"] is None
    assert not session_file.exists()
    assert not stray.exists()

    status = await service.status()
    assert status["status"] != ACCOUNT_LOGGED_IN
    assert status["user"] is None
    assert status["logged_in_at"] is None

    account = await _account(database)
    assert account is not None
    assert account.status != ACCOUNT_LOGGED_IN
    # Nomor telepon disimpan agar admin mudah login lagi.
    assert account.phone == _PHONE


async def test_logout_tetap_berhasil_walau_gagal_di_sisi_telegram(
    service: TelegramLoginService, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = await service.start(_PHONE)
    await service.verify(start.flow_id, _CODE)

    async def failing_log_out(self: FakeClient) -> None:
        raise ConnectionError("tidak terjangkau")

    monkeypatch.setattr(FakeClient, "log_out", failing_log_out)
    result = await service.logout()

    assert result["remote_error"] == "network_error"
    assert result["removed_session_files"] >= 1
    assert not service.session_path("userbot_session").exists()
    status = await service.status()
    assert status["status"] != ACCOUNT_LOGGED_IN


async def test_status_menandai_perlu_login_ulang_saat_nama_sesi_diubah(
    service: TelegramLoginService, store: SettingsStore
) -> None:
    start = await service.start(_PHONE)
    await service.verify(start.flow_id, _CODE)

    await store.update({"telegram_session_name": "sesi_lain"}, actor="test")

    status = await service.status()
    # Data akun dipertahankan, hanya ditandai perlu login ulang (Q10).
    assert status["status"] == ACCOUNT_LOGGED_IN
    assert status["session_mismatch"] is True
    assert status["session_name"] == "sesi_lain"


async def test_status_turun_jadi_logged_out_bila_berkas_sesi_hilang(
    service: TelegramLoginService, tmp_path: Path
) -> None:
    start = await service.start(_PHONE)
    await service.verify(start.flow_id, _CODE)
    service.session_path("userbot_session").unlink()

    status = await service.status()
    assert status["status"] == "logged_out"


async def test_flow_dipakai_lagi_setelah_restart_proses(
    database: Database, store: SettingsStore, tmp_path: Path
) -> None:
    """Klien hilang dari memori (proses web restart) tetapi flow di DB masih hidup."""
    await store.update(
        {"telegram_api_id": _API_ID, "telegram_api_hash": _API_HASH}, actor="test"
    )
    data_dir = tmp_path / "data"
    first = TelegramLoginService(
        database, store, data_dir=data_dir, client_factory=FakeTelegram.factory
    )
    start = await first.start(_PHONE)

    # Simulasi restart: instance baru dengan state memori kosong.
    second = TelegramLoginService(
        database, store, data_dir=data_dir, client_factory=FakeTelegram.factory
    )
    result = await second.verify(start.flow_id, _CODE)

    assert result.next == "done"
    assert FakeTelegram.instances[-1].signed_in_with == (
        _PHONE,
        _CODE,
        SECRET_CODE_HASH,
    )


# ------------------------------------------------------------------- keamanan


async def _jalankan_seluruh_alur(service: TelegramLoginService) -> None:
    """Login 2FA sukses, lalu percobaan gagal dengan kode lain, lalu logout."""
    FakeTelegram.sign_in_error = SessionPasswordNeeded()
    start = await service.start(_PHONE)
    await service.verify(start.flow_id, _CODE)
    await service.submit_password(start.flow_id, _2FA_PASSWORD)

    FakeTelegram.sign_in_error = PhoneCodeInvalid()
    ulang = await service.start(_PHONE)
    with pytest.raises(TelegramLoginError):
        await service.verify(ulang.flow_id, _WRONG_CODE)

    await service.cleanup_expired()
    await service.logout()


#: Nilai sensitif yang tidak boleh muncul di log telegent maupun log panel.
_RAHASIA = (SECRET_CODE_HASH, _2FA_PASSWORD, _CODE, _WRONG_CODE, _API_HASH)


async def test_tidak_pernah_log_kode_password_atau_hash(
    service: TelegramLoginService, caplog: pytest.LogCaptureFixture
) -> None:
    """Log milik telegent tidak boleh memuat kode OTP, password, atau code hash."""
    caplog.set_level(logging.DEBUG, logger="telegent")

    await _jalankan_seluruh_alur(service)

    teks = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("telegent")
    )
    for rahasia in _RAHASIA:
        assert rahasia not in teks, f"rahasia bocor ke log: {rahasia[:6]}…"


async def test_log_panel_meredaksi_bahwa_pun_terbocor_pustaka_lain(
    database: Database, store: SettingsStore, tmp_path: Path
) -> None:
    """Handler log panel (yang dilihat admin) meredaksi nilai sensitif apa pun.

    Lapis kedua: pustaka pihak ketiga (mis. driver SQLite pada level DEBUG) bisa
    mencetak nilai sebagai argumen query. `SecretRedactor` menutup kebocoran itu.
    """
    redactor = SecretRedactor()
    buffer = LogRingBuffer()
    bus = EventBus()
    handler = BusLogHandler(bus, buffer, redactor)
    root = logging.getLogger()
    root_level = root.level
    root.setLevel(logging.DEBUG)  # skenario terburuk: admin memakai log_level=DEBUG
    root.addHandler(handler)
    try:
        await store.update(
            {"telegram_api_id": _API_ID, "telegram_api_hash": _API_HASH}, actor="test"
        )
        service = TelegramLoginService(
            database,
            store,
            data_dir=tmp_path / "data",
            redactor=redactor,
            client_factory=FakeTelegram.factory,
        )
        await _jalankan_seluruh_alur(service)
        # Simulasikan pustaka lain yang mencetak nilai sensitif sebagai argumen SQL.
        logging.getLogger("aiosqlite.core").debug(
            f"INSERT INTO login_flow VALUES ({SECRET_CODE_HASH!r}, {_2FA_PASSWORD!r})"
        )
    finally:
        root.removeHandler(handler)
        root.setLevel(root_level)

    teks = "\n".join(entry["message"] for entry in buffer.recent())
    for rahasia in _RAHASIA:
        assert rahasia not in teks, f"rahasia bocor ke log panel: {rahasia[:6]}…"
    assert "[REDACTED]" in teks


async def test_redactor_mendaftarkan_phone_code_hash(
    database: Database, store: SettingsStore, tmp_path: Path
) -> None:
    redactor = SecretRedactor()
    await store.update(
        {"telegram_api_id": _API_ID, "telegram_api_hash": _API_HASH}, actor="test"
    )
    service = TelegramLoginService(
        database,
        store,
        data_dir=tmp_path / "data",
        redactor=redactor,
        client_factory=FakeTelegram.factory,
    )

    await service.start(_PHONE)

    assert redactor.redact(f"hash={SECRET_CODE_HASH}") == "hash=[REDACTED]"
    assert redactor.redact(f"hash={_API_HASH}") == "hash=[REDACTED]"