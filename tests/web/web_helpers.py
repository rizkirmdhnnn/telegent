"""Helper pengujian web panel."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from telegent.web.security import CSRF_COOKIE
from telegent.web.telegram_login import TelegramCredentials

DEFAULT_PASSWORD = "rahasia-kuat-123"

#: Nilai sensitif yang tidak boleh muncul di log mana pun pada pengujian.
SECRET_CODE_HASH = "hash-rahasia-yang-panjang-sekali"


def csrf_of(client: TestClient) -> str:
    """Token CSRF dari cookie (untuk header mutasi)."""
    token = client.cookies.get(CSRF_COOKIE)
    assert token, "cookie CSRF belum dipasang"
    return token


def do_setup(
    client: TestClient, username: str = "admin", password: str = DEFAULT_PASSWORD
) -> TestClient:
    """Jalankan wizard setup (admin langsung login)."""
    resp = client.post(
        "/api/setup/admin", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return client


def do_login(
    client: TestClient,
    username: str = "admin",
    password: str = DEFAULT_PASSWORD,
    **extra: object,
):
    """Kirim permintaan login (mengembalikan respons)."""
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password, **extra},
    )


def login(
    client: TestClient, username: str = "admin", password: str = DEFAULT_PASSWORD
) -> TestClient:
    """Login dan pastikan berhasil."""
    resp = do_login(client, username, password)
    assert resp.status_code == 200, resp.text
    return client

# ------------------------------------------------------- fake Pyrogram (login)


class FakeTelegramClient:
    """Klien Pyrogram minimal: hanya operasi yang dipakai layanan login.

    Menerima dua cara pemanggilan agar bisa dipakai sebagai pengganti
    `ClientFactory` sekaligus dijemput langsung pada `Client` bawaan:
    `FakeTelegramClient(credentials, workdir)` dan `Client(session_name, ...)`.
    """

    def __init__(
        self,
        credentials: "TelegramCredentials | str",
        workdir: Path | str | None = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(credentials, TelegramCredentials):
            self.credentials = credentials
            self.workdir = Path(workdir or ".")
        else:
            # Dipanggil seperti `Client(session_name, api_id=..., workdir=...)`.
            # `workdir` masuk ke parameter bernama, bukan ke `**kwargs`.
            self.credentials = TelegramCredentials(
                api_id=int(kwargs.get("api_id") or 0),
                api_hash=str(kwargs.get("api_hash") or ""),
                session_name=credentials,
            )
            self.workdir = Path(workdir if workdir is not None else ".")
        self.name = self.credentials.session_name
        self.api_id = self.credentials.api_id
        self.api_hash = self.credentials.api_hash
        self.started = False
        self.stopped = False
        self.is_connected = False
        self.logged_out = False
        self.sent_to: str | None = None
        self.signed_in_with: tuple[str, str, str | None] | None = None
        self.checked_password: str | None = None
        # Pyrogram membuat berkas sesi begitu klien dijalankan.
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / f"{self.name}.session").write_bytes(b"fake-session")
        FakeTelegram.instances.append(self)

    async def start(self) -> None:
        # `Client.start()` pada Pyrogram memancing prompt nomor telepon di stdin
        # bila sesi belum terotorisasi. Klien login TIDAK BOLEH memakainya.
        raise AssertionError(
            "klien login tidak boleh memakai start(): itu memicu prompt stdin"
        )

    async def connect(self) -> bool:
        self.is_connected = True
        # Dibaca dari kelas supaya bisa diatur per-skenario pengujian.
        return FakeTelegram.authorized

    async def disconnect(self) -> None:
        self.is_connected = False
        self.stopped = True

    async def initialize(self) -> None:
        self.initialized = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_code(self, phone: str) -> Any:
        if FakeTelegram.send_code_error is not None:
            raise FakeTelegram.send_code_error
        self.sent_to = phone
        return SimpleNamespace(phone_code_hash=FakeTelegram.phone_code_hash)

    async def sign_in(
        self, phone_number: str, phone_code_hash: str, phone_code: str
    ) -> Any:
        """Tanda tangan meniru Pyrogram persis: (phone, hash, code).

        Sengaja TIDAK memakai keyword-only atau urutan lain. Kesalahan nyata
        (2026-10-11): kode OTP dikirim pada slot `phone_code_hash`, sehingga
        fake versi lama ikut Strengthening bug itu.
        """
        self.signed_in_with = (phone_number, phone_code_hash, phone_code)
        if FakeTelegram.sign_in_error is not None:
            raise FakeTelegram.sign_in_error
        return FakeTelegram.me

    async def check_password(self, password: str) -> Any:
        self.checked_password = password
        if FakeTelegram.password_error is not None:
            raise FakeTelegram.password_error
        return FakeTelegram.me

    async def get_me(self) -> Any:
        if FakeTelegram.get_me_error is not None:
            raise FakeTelegram.get_me_error
        return FakeTelegram.me

    async def log_out(self) -> None:
        self.logged_out = True


class FakeTelegram:
    """Pabrik klien palsu yang digerakkan skenario per pengujian."""

    sign_in_error: BaseException | None = None
    password_error: BaseException | None = None
    send_code_error: BaseException | None = None
    get_me_error: BaseException | None = None
    #: False → `connect()` mengembalikan False (sesi belum terotorisasi).
    authorized: bool = True
    phone_code_hash: str = SECRET_CODE_HASH
    me: Any = SimpleNamespace(id=5550001, username="telegent_bot", first_name="Telegent")
    instances: list[FakeTelegramClient] = []

    @classmethod
    def reset(cls) -> None:
        cls.authorized = True
        cls.sign_in_error = None
        cls.password_error = None
        cls.send_code_error = None
        cls.get_me_error = None
        cls.instances.clear()

    @classmethod
    def factory(
        cls, credentials: TelegramCredentials, workdir: Path
    ) -> FakeTelegramClient:
        return FakeTelegramClient(credentials, workdir)


@pytest.fixture
def fake_telegram():
    """Reset skenario fake Pyrogram; pasang sendiri bila perlu."""
    FakeTelegram.reset()
    yield FakeTelegram
    FakeTelegram.reset()
