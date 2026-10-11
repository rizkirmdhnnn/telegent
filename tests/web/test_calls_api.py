"""Test API pemantauan: panggilan aktif, riwayat, detail, hangup, ekspor (E2).

Semua tes memakai client FastAPI dengan database ter-migrasi dan admin yang
sudah login. Tidak ada jaringan: sesi panggilan aktif dibuat lewat stub, dan
penyemianan data memakai engine terpisah terhadap DB yang sama (pola `test_audit`).
"""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from web_helpers import csrf_of, do_setup

from telegent.telegram.call_session import SessionState
from telegent.web.bootstrap import BootstrapConfig
from telegent.web.db import models
from telegent.web.db.base import Database


# ------------------------------------------------------------------- fixture


@pytest.fixture
def admin_client(live_client: TestClient) -> TestClient:
    """Admin yang sudah lewat wizard setup."""
    do_setup(live_client)
    return live_client


def _seed(db_url: str, calls: list[dict[str, Any]]) -> list[int]:
    """Sisipkan `call_record` dari luar loop aplikasi (engine terpisah)."""

    async def run() -> list[int]:
        db = Database(db_url)
        try:
            async with db.session() as session:
                rows = []
                for spec in calls:
                    row = models.CallRecord(
                        tg_call_id=spec.get("tg_call_id", 1),
                        user_id=spec.get("user_id", 100),
                        user_display=spec.get("user_display"),
                        outcome=spec.get("outcome", "answered"),
                        end_reason=spec.get("end_reason", "caller_hangup"),
                        started_at=spec.get("started_at", datetime(2026, 1, 1, 10, 0, 0)),
                        ended_at=spec.get("ended_at"),
                        duration_sec=spec.get("duration_sec", 30),
                        transcript_count=spec.get("transcript_count", 0),
                        tool_call_count=spec.get("tool_call_count", 0),
                    )
                    session.add(row)
                    rows.append(row)
                await session.flush()
                return [int(row.id) for row in rows]
        finally:
            await db.dispose()

    return asyncio.run(run())


def _seed_children(
    db_url: str,
    record_id: int,
    *,
    transcripts: list[tuple[str, str]] = (),
    tools: list[dict[str, Any]] = (),
    at: datetime | None = None,
) -> None:
    """Sisipkan transkrip & tool call untuk satu `call_record`."""

    async def run() -> None:
        db = Database(db_url)
        try:
            async with db.session() as session:
                for speaker, text in transcripts:
                    session.add(
                        models.TranscriptEntry(
                            call_record_id=record_id, speaker=speaker, text=text, at=at
                        )
                    )
                for spec in tools:
                    session.add(
                        models.ToolCallRecord(
                            call_record_id=record_id,
                            name=spec["name"],
                            args_json=spec.get("args_json"),
                            result_json=spec.get("result_json"),
                            status=spec.get("status", "ok"),
                            duration_ms=spec.get("duration_ms", 10),
                            at=at,
                        )
                    )
        finally:
            await db.dispose()

    asyncio.run(run())


def _count_calls(client: TestClient) -> int:
    async def run() -> int:
        from sqlalchemy import func, select

        db: Database = client.app.state.db  # type: ignore[attr-defined]
        async with db.session() as session:
            return int(
                (await session.execute(select(func.count()).select_from(models.CallRecord))).scalar_one()
            )

    return asyncio.run(run())


@pytest.fixture
def db_url_of(bootstrap: BootstrapConfig) -> str:
    return bootstrap.db_url


class _FakeSession:
    """Sesi panggilan tiruan yang mencatat `schedule_hangup`."""

    def __init__(self, user_id: int = 100, call_id: int = 1) -> None:
        self.user_id = user_id
        self.call_id = call_id
        self.state = SessionState.ACTIVE
        self.duration_seconds = 42
        self.end_reason: str | None = None
        self.hangups: list[str | None] = []

    def schedule_hangup(self, min_wait: float = 0.0, *, reason: str = "ai_end_call") -> None:
        self.hangups.append(reason)


class _FakeApp:
    """`TelegentApp` tiruan yang hanya melayani pembacaan sesi."""

    def __init__(self, sessions: list[_FakeSession]) -> None:
        self._sessions = sessions

    def active_sessions(self) -> list[_FakeSession]:
        return list(self._sessions)

    def active_call_count(self) -> int:
        return len(self._sessions)

    def status_payload(self) -> dict[str, Any]:
        return {"running": True, "active_calls": len(self._sessions)}

    async def stop(self) -> None: ...

    async def shutdown(self) -> None: ...


#: Sesi yang dipalsukan, dikembalikan lagi setelah tiap tes.
_STUBBED: list[tuple[Any, Any]] = []


@pytest.fixture(autouse=True)
def _restore_runtime() -> Any:
    _STUBBED.clear()
    yield
    for runtime, original in _STUBBED:
        runtime._app = original
    _STUBBED.clear()


def _stub_runtime(client: TestClient, sessions: list[_FakeSession]) -> None:
    """Pasang sesi palsu pada `TelegentApp` milik runtime controller."""
    runtime = client.app.state.runtime
    _STUBBED.append((runtime, runtime._app))
    runtime._app = _FakeApp(sessions)  # type: ignore[assignment]


def _flush(client: TestClient) -> None:
    """Jalankan antrean perekam pada event loop aplikasi (dari tes sinkron)."""
    recorder = client.app.state.call_recorder
    client.portal.call(recorder.flush)  # type: ignore[union-attr]


# -------------------------------------------------------------- active calls


def test_calls_active_kosong_saat_bot_berhenti(admin_client: TestClient) -> None:
    """Bot mati bukan galat — daftar kosong agar UI tak perlu dua jalur."""
    resp = admin_client.get("/api/calls/active")
    assert resp.status_code == 200
    assert resp.json() == {"calls": [], "count": 0}


def test_calls_active_menampilkan_sesi_berjalan(
    admin_client: TestClient,
) -> None:
    session = _FakeSession(user_id=555, call_id=77)
    _stub_runtime(admin_client, [session])
    recorder = admin_client.app.state.call_recorder
    recorder.call_incoming(77, 555)
    recorder.call_started(77, 555)
    recorder.session_event(77, "transcript", {"speaker": "caller", "text": "halo"})
    _flush(admin_client)

    resp = admin_client.get("/api/calls/active")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    item = data["calls"][0]
    assert item["user_id"] == 555
    assert item["tg_call_id"] == 77
    assert item["state"] == "ACTIVE"
    assert item["duration_sec"] == 42
    assert item["transcript_tail"] == [{"speaker": "caller", "text": "halo"}]
    assert item["record_id"] is not None


def test_calls_active_membutuhkan_sesi_admin(live_client: TestClient) -> None:
    assert live_client.get("/api/calls/active").status_code == 401


# ------------------------------------------------------------------- riwayat


def test_calls_daftar_kosong_saat_belum_ada_data(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/calls")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "total_pages": 0,
    }


def test_calls_daftar_dengan_paginasi(admin_client: TestClient, db_url_of: str) -> None:
    _seed(
        db_url_of,
        [
            {
                "tg_call_id": index,
                "user_id": 100 + index,
                "started_at": datetime(2026, 1, 1, 10, index, 0),
            }
            for index in range(1, 6)
        ],
    )

    resp = admin_client.get("/api/calls", params={"page": 2, "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert body["page"] == 2
    assert [item["tg_call_id"] for item in body["items"]] == [3, 2]


def test_calls_daftar_filter_user_dan_outcome(admin_client: TestClient, db_url_of: str) -> None:
    _seed(
        db_url_of,
        [
            {"tg_call_id": 1, "user_id": 111, "outcome": "answered"},
            {"tg_call_id": 2, "user_id": 222, "outcome": "rejected_whitelist"},
            {"tg_call_id": 3, "user_id": 111, "outcome": "rejected_ratelimit"},
        ],
    )

    by_user = admin_client.get("/api/calls", params={"user": 111}).json()
    assert by_user["total"] == 2

    by_outcome = admin_client.get("/api/calls", params={"outcome": "answered"}).json()
    assert by_outcome["total"] == 1
    assert by_outcome["items"][0]["outcome"] == "answered"


def test_calls_daftar_filter_rentang_waktu(admin_client: TestClient, db_url_of: str) -> None:
    _seed(
        db_url_of,
        [
            {"tg_call_id": 1, "started_at": datetime(2026, 1, 1, 10, 0)},
            {"tg_call_id": 2, "started_at": datetime(2026, 2, 1, 10, 0)},
        ],
    )

    body = admin_client.get(
        "/api/calls", params={"from": "2026-01-15", "to": "2026-03-01"}
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["tg_call_id"] == 2


def test_calls_daftar_menolak_outcome_asing(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/calls", params={"outcome": "entah"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_filter"


def test_calls_daftar_menolak_tanggal_asing(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/calls", params={"from": "bukan-tanggal"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_filter"


def test_calls_get_bersifat_baca_tidak_menulis(
    admin_client: TestClient, db_url_of: str
) -> None:
    """Aturan #3: `GET` tidak boleh menulis; jumlah baris tetap sama."""
    ids = _seed(db_url_of, [{"tg_call_id": 1}])
    before = _count_calls(admin_client)

    assert admin_client.get("/api/calls").status_code == 200
    assert admin_client.get(f"/api/calls/{ids[0]}").status_code == 200
    assert admin_client.get(f"/api/calls/{ids[0]}/transcript").status_code == 200
    assert admin_client.get(f"/api/calls/{ids[0]}/tools").status_code == 200

    assert _count_calls(admin_client) == before


# -------------------------------------------------------------------- detail


def test_calls_detail_dan_transkrip_tool(
    admin_client: TestClient, db_url_of: str
) -> None:
    record_id = _seed(
        db_url_of, [{"tg_call_id": 1, "user_id": 111, "transcript_count": 2}]
    )[0]
    _seed_children(
        db_url_of,
        record_id,
        transcripts=[("caller", "halo"), ("ai", "hai")],
        tools=[
            {
                "name": "end_call",
                "args_json": '{"reason": "pamit"}',
                "result_json": '{"status": "ending_call"}',
                "duration_ms": 15,
            }
        ],
    )

    detail = admin_client.get(f"/api/calls/{record_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == record_id
    assert body["transcript_count"] == 2
    assert body["active"] is False

    transcript = admin_client.get(f"/api/calls/{record_id}/transcript").json()
    assert [item["speaker"] for item in transcript["items"]] == ["caller", "ai"]
    assert transcript["total"] == 2

    tools = admin_client.get(f"/api/calls/{record_id}/tools").json()
    assert tools["total"] == 1
    assert tools["items"][0]["args"] == {"reason": "pamit"}
    assert tools["items"][0]["result"] == {"status": "ending_call"}


def test_calls_detail_menandai_panggilan_aktif(
    admin_client: TestClient, db_url_of: str
) -> None:
    ids = _seed(db_url_of, [{"tg_call_id": 42, "user_id": 9}])
    _stub_runtime(admin_client, [_FakeSession(user_id=9, call_id=42)])

    body = admin_client.get(f"/api/calls/{ids[0]}").json()
    assert body["active"] is True


def test_waktu_panggilan_selalu_utc_dengan_suffix_z(
    admin_client: TestClient, db_url_of: str
) -> None:
    """Kolom disimpan sebagai naive UTC; API harus menandainya eksplisit.

    Tanpa akhiran `Z`, `new Date()` di browser memperlakukannya sebagai waktu
    lokal sehingga daftar panggilan terlihat bergeser satu jam.
    """
    record_id = _seed(db_url_of, [{"tg_call_id": 1, "ended_at": datetime(2026, 1, 1, 10, 1)}])[0]
    _seed_children(
        db_url_of,
        record_id,
        transcripts=[("caller", "halo")],
        tools=[{"name": "end_call"}],
        at=datetime(2026, 1, 1, 10, 0, 30),
    )

    items = admin_client.get("/api/calls").json()["items"]
    list_body = next(item for item in items if item["id"] == record_id)
    detail = admin_client.get(f"/api/calls/{record_id}").json()
    transcript = admin_client.get(f"/api/calls/{record_id}/transcript").json()["items"][0]
    tools = admin_client.get(f"/api/calls/{record_id}/tools").json()["items"][0]

    for value in (
        list_body["started_at"],
        list_body["ended_at"],
        detail["started_at"],
        detail["ended_at"],
        transcript["at"],
        tools["at"],
    ):
        assert value is not None, "waktu tidak boleh null pada data contoh"
        assert value.endswith("Z"), f"waktu harus berakhiran Z, dapat: {value}"
        # Naive UTC harus dibaca apa adanya sebagai UTC (jam 10 tetap 10).
        assert datetime.fromisoformat(value.replace("Z", "+00:00")).hour == 10


def test_calls_detail_tidak_ada_menghasilkan_404(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/calls/999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "call_not_found"


@pytest.mark.parametrize(
    "suffix", ["/transcript", "/tools"], ids=["transcript", "tools"]
)
def test_calls_subresource_tidak_ada_menghasilkan_404(
    admin_client: TestClient, suffix: str
) -> None:
    resp = admin_client.get(f"/api/calls/999{suffix}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "call_not_found"


# -------------------------------------------------------------------- hangup


def test_hangup_menutup_panggilan_aktif(admin_client: TestClient, db_url_of: str) -> None:
    ids = _seed(db_url_of, [{"tg_call_id": 42, "user_id": 9}])
    session = _FakeSession(user_id=9, call_id=42)
    _stub_runtime(admin_client, [session])

    resp = admin_client.post(
        f"/api/calls/{ids[0]}/hangup", headers={"X-CSRF-Token": csrf_of(admin_client)}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert session.hangups == ["panel_hangup"]


def test_hangup_mencatat_audit(admin_client: TestClient, db_url_of: str) -> None:
    ids = _seed(db_url_of, [{"tg_call_id": 42, "user_id": 9}])
    _stub_runtime(admin_client, [_FakeSession(user_id=9, call_id=42)])

    admin_client.post(
        f"/api/calls/{ids[0]}/hangup", headers={"X-CSRF-Token": csrf_of(admin_client)}
    )

    audit = admin_client.get("/api/audit", params={"action": "call.hangup"}).json()
    assert audit["total"] == 1
    assert audit["items"][0]["actor"] == "admin"
    assert audit["items"][0]["target"] == "call"
    assert audit["items"][0]["after"] == {"requested": True}


def test_hangup_ditolak_bila_panggilan_tidak_aktif_dan_tercatat(
    admin_client: TestClient, db_url_of: str
) -> None:
    ids = _seed(db_url_of, [{"tg_call_id": 42}])
    _stub_runtime(admin_client, [])  # tidak ada sesi aktif

    resp = admin_client.post(
        f"/api/calls/{ids[0]}/hangup", headers={"X-CSRF-Token": csrf_of(admin_client)}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "call_not_active"

    audit = admin_client.get("/api/audit", params={"action": "call.hangup"}).json()
    assert audit["total"] == 1
    assert audit["items"][0]["after"] == {"error": "call_not_active"}


def test_hangup_ditolak_bila_record_tidak_ada_dan_tercatat(
    admin_client: TestClient,
) -> None:
    resp = admin_client.post(
        "/api/calls/999/hangup", headers={"X-CSRF-Token": csrf_of(admin_client)}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "call_not_found"

    audit = admin_client.get("/api/audit", params={"action": "call.hangup"}).json()
    assert audit["total"] == 1
    assert audit["items"][0]["after"] == {"error": "call_not_found"}


def test_hangup_membutuhkan_csrf(admin_client: TestClient, db_url_of: str) -> None:
    ids = _seed(db_url_of, [{"tg_call_id": 42}])
    _stub_runtime(admin_client, [_FakeSession(call_id=42)])

    resp = admin_client.post(f"/api/calls/{ids[0]}/hangup")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


def test_hangup_membutuhkan_sesi_admin(live_client: TestClient) -> None:
    assert live_client.post("/api/calls/1/hangup").status_code == 401


# ------------------------------------------------------------------- ekspor


def test_ekspor_csv_menghormati_filter(admin_client: TestClient, db_url_of: str) -> None:
    _seed(
        db_url_of,
        [
            {"tg_call_id": 1, "user_id": 111, "outcome": "answered"},
            {"tg_call_id": 2, "user_id": 222, "outcome": "rejected_whitelist"},
            {"tg_call_id": 3, "user_id": 111, "outcome": "answered"},
        ],
    )

    resp = admin_client.get("/api/calls/export", params={"user": 111})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "telegent-calls.csv" in resp.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 2
    assert {row["user_id"] for row in rows} == {"111"}
    assert rows[0]["outcome"] == "answered"
    # Waktu diekspor dalam ISO + Z, sama dengan format di seluruh API.
    assert rows[0]["started_at"].endswith("Z")


def test_ekspor_csv_mencakup_seluruh_hasil_filter_bukan_hanya_halaman(
    admin_client: TestClient, db_url_of: str
) -> None:
    _seed(
        db_url_of,
        [{"tg_call_id": index, "user_id": 100} for index in range(1, 8)],
    )

    resp = admin_client.get("/api/calls/export", params={"page_size": 2})
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 7


def test_ekspor_csv_menolak_outcome_asing(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/calls/export", params={"outcome": "entah"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_filter"


def test_ekspor_csv_membutuhkan_sesi_admin(live_client: TestClient) -> None:
    assert live_client.get("/api/calls/export").status_code == 401