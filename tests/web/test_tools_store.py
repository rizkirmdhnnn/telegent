"""Test lapisan penyimpanan tool (`telegent.web.tools_store`).

Fokus: data rusak di tabel `tool_config` tidak boleh menjatuhkan runtime. Bot
menjalankan tool bawaan dengan konfigurasi default, jadi baris JSON yang tidak
baca harus diabaikan, bukan diteruskan ke `ToolRegistry`.
"""

from __future__ import annotations



from telegent.web.db import models
from telegent.web.db.base import Database
from telegent.web.tools_store import (
    load_tool_settings,
    save_tool_setting,
    tool_configs_for_runtime,
)


async def test_simpan_dan_muat_konfigurasi(database: Database) -> None:
    _, sesudah = await save_tool_setting(
        database, "get_current_datetime", enabled=False, config={"timezone": "Asia/Jakarta"}
    )

    assert sesudah.enabled is False
    assert sesudah.config == {"timezone": "Asia/Jakarta"}

    dimuat = await load_tool_settings(database)
    assert dimuat["get_current_datetime"].config == {"timezone": "Asia/Jakarta"}


async def test_simpan_tanpa_config_tetap_menyimpan_status(database: Database) -> None:
    _, sesudah = await save_tool_setting(database, "end_call", enabled=False)

    assert sesudah.enabled is False
    assert sesudah.config is None


async def test_nilai_default_bila_baris_belum_ada(database: Database) -> None:
    sebelum, _ = await save_tool_setting(database, "tool_baru", enabled=True)

    assert sebelum.enabled is True  # default tool aktif
    assert sebelum.config is None


async def test_config_rusak_diabaikan(database: Database) -> None:
    """JSON tidak valid tidak boleh membuat runtime gagal start."""
    async with database.session() as session:
        session.add(
            models.ToolConfig(name="rusak", enabled=True, config_json="{bukan-json")
        )

    dimuat = await load_tool_settings(database)

    assert dimuat["rusak"].config is None
    assert dimuat["rusak"].enabled is True


async def test_config_bukan_dikson_diabaikan(database: Database) -> None:
    """JSON valid tetapi bukan objek (mis. array) tidak boleh dipakai."""
    async with database.session() as session:
        session.add(models.ToolConfig(name="array", enabled=True, config_json="[1,2,3]"))

    dimuat = await load_tool_settings(database)

    assert dimuat["array"].config is None


async def test_config_kosong_diabaikan(database: Database) -> None:
    async with database.session() as session:
        session.add(models.ToolConfig(name="kosong", enabled=True, config_json=""))

    dimuat = await load_tool_settings(database)

    assert dimuat["kosong"].config is None


async def test_hidrasi_runtime_hanya_memakai_config_valid(
    database: Database,
) -> None:
    """Baris rusak tidak boleh ikut terbawa ke `ToolRegistry` saat start."""
    async with database.session() as session:
        session.add(models.ToolConfig(name="rusak", enabled=True, config_json="{oops"))

    await save_tool_setting(database, "end_call", config={"min_sec": 1})

    hasil = await tool_configs_for_runtime(database)

    assert hasil == {"end_call": {"min_sec": 1}}


async def test_perubahan_tercatat_untuk_audit(database: Database) -> None:
    await save_tool_setting(database, "end_call", enabled=True, config={"min_sec": 1})

    sebelum, sesudah = await save_tool_setting(
        database, "end_call", enabled=False, config={"min_sec": 5}
    )

    assert sebelum.enabled is True
    assert sebelum.config == {"min_sec": 1}
    assert sesudah.enabled is False
    assert sesudah.config == {"min_sec": 5}


async def test_config_tetap_ada_bila_hanya_status_diubah(database: Database) -> None:
    """Tidak mengirim `config` tidak boleh menghapus konfigurasi yang tersimpan."""
    await save_tool_setting(database, "end_call", config={"min_sec": 1})

    _, sesudah = await save_tool_setting(database, "end_call", enabled=False)

    assert sesudah.enabled is False
    assert sesudah.config == {"min_sec": 1}


async def test_tabel_kosong_tidak_menghasilkan_apapun(database: Database) -> None:
    assert await load_tool_settings(database) == {}
    assert await tool_configs_for_runtime(database) == {}


async def test_load_tool_settings_tidak_menulis(database: Database) -> None:
    """Endpoint baca tidak boleh menulis apa pun (aturan #3)."""
    await save_tool_setting(database, "end_call", config={"min_sec": 1})

    async with database.session() as session:
        sebelum = len((await session.execute(models.ToolConfig.__table__.select())).all())

    await load_tool_settings(database)
    await tool_configs_for_runtime(database)

    async with database.session() as session:
        sesudah = len((await session.execute(models.ToolConfig.__table__.select())).all())

    assert sebelum == sesudah


def test_tool_setting_beku() -> None:
    """`ToolSetting` dipakai sebagai nilai sebelum/sesudah pada audit."""
    from dataclasses import FrozenInstanceError

    from telegent.web.tools_store import ToolSetting

    setting = ToolSetting(name="end_call", enabled=True, config=None)
    try:
        setting.enabled = False  # type: ignore[misc]
    except FrozenInstanceError:
        return
    raise AssertionError("ToolSetting harus immutable (beku)")