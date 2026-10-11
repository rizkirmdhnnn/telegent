"""Jembatan runtime bot → penyimpanan panggilan & event bus (tiket E1).

`CallRecorder` adalah "perekam" yang dipasang `TelegentApp` sebagai
`CallObserver`. Aturan yang dijaga di sini:

* **Jalur audio tidak boleh melambat.** Semua hook adalah fungsi sinkron tanpa
  `await`; satu-satunya kerja yang dilakukan adalah mengantrekan pekerjaan dan
  meneruskan event ke `EventBus` (yang memang *drop* saat pengikut lambat).
* **Tidak ada penulisan langsung di jalur panggilan.** Satu task penulis
  tunggal (`_writer`) mengambil antrean dan menulis ke SQLite, sehingga urutan
  tulis terjamin (record panggilan dibuat sebelum transkripnya).
* **Antrean penuh = buang, jangan tunggu.** Kalau database lambat, data
  monitoring boleh hilang; audio tidak boleh tersendat.
* **`store_transcripts=false` mematikan penyimpanan teks** (Q13), termasuk
  penerusan ke bus; tool call tetap disimpan karena bukan rekaman suara.
* **Redaksi secret tetap berlaku** pada transkrip, argumen, dan hasil tool.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Callable

from telegent.ai.tools.spec import TOOL_STATUS_OK
from telegent.web import call_store
from telegent.web.db.base import Database, utcnow
from telegent.web.events import EventBus
from telegent.web.log_stream import SecretRedactor
from telegent.web.settings_store import SettingsStore

log = logging.getLogger("telegent.web.call_recorder")

#: Batas antrean pekerjaan; saat penuh, pekerjaan monitoring dibuang (aturan audio).
DEFAULT_QUEUE_SIZE = 1000

#: Berapa banyak pekerjaan yang ditulis dalam satu giliran task penulis.
WRITE_BATCH = 32

#: Berapa banyak baris transkrip terakhir yang diingat untuk panggilan aktif.
TRANSCRIPT_TAIL = 10

#: Nama event bus (spesifikasi §7).
EVENT_CALL_INCOMING = "call.incoming"
EVENT_CALL_STARTED = "call.started"
EVENT_CALL_ENDED = "call.ended"
EVENT_TRANSCRIPT = "transcript"
EVENT_TOOL_CALL = "tool_call"


@dataclass
class _CallState:
    """Status satu panggilan yang sedang dipantau di memori."""

    tg_call_id: int
    user_id: int
    record_id: int | None = None
    transcript_count: int = 0
    tool_call_count: int = 0
    tail: list[dict[str, Any]] = field(default_factory=list)


class CallRecorder:
    """Merekam siklus hidup panggilan ke database dan menyiarkannya ke bus."""

    def __init__(
        self,
        db: Database,
        *,
        bus: EventBus | None = None,
        redactor: SecretRedactor | None = None,
        queue_size: int = DEFAULT_QUEUE_SIZE,
    ) -> None:
        self._db = db
        self._bus = bus
        self._redactor = redactor
        self._queue: asyncio.Queue[Callable[[], Any] | None] = asyncio.Queue(
            maxsize=max(1, queue_size)
        )
        self._states: dict[int, _CallState] = {}
        self._writer: asyncio.Task[None] | None = None
        self._store_transcripts = True
        #: Jumlah pekerjaan yang dibuang karena antrean penuh.
        self.dropped = 0

    # -------------------------------------------------------------- lifecycle

    def set_store_transcripts(self, enabled: bool) -> None:
        """Terapkan setting `store_transcripts` saat berubah."""
        self._store_transcripts = bool(enabled)

    @property
    def store_transcripts(self) -> bool:
        """True bila teks transkrip boleh disimpan & disiarkan."""
        return self._store_transcripts

    def start(self) -> None:
        """Nyalakan task penulis (aman dipanggil berulang)."""
        if self._writer is None:
            self._writer = asyncio.create_task(self._run_writer(), name="telegent-call-recorder")

    async def aclose(self) -> None:
        """Tunggu antrean kosong lalu hentikan task penulis (idempoten)."""
        writer = self._writer
        if writer is None:
            return
        if self._enqueue_sentinel():
            with suppress(asyncio.CancelledError):
                await writer
        else:
            # Antrean jenuh: sisa pekerjaan dibuang, tidak ada yang menunggu.
            log.warning("Antrean pencatatan panggilan penuh saat shutdown.")
            writer.cancel()
            with suppress(asyncio.CancelledError):
                await writer
        self._writer = None

    async def flush(self) -> None:
        """Tunggu sampai seluruh antrean pekerjaan selesai (dipakai pengujian)."""
        await self._queue.join()

    def _enqueue_sentinel(self) -> bool:
        """Penanda berhenti; False bila antrean sudah penuh."""
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            return False
        return True

    # ------------------------------------------------------- CallObserver API

    def call_incoming(
        self, tg_call_id: int, user_id: int, *, user_display: str | None = None
    ) -> None:
        """Panggilan masuk (termasuk yang akan ditolak — Q12)."""
        state = self._state(tg_call_id, user_id)
        self._publish(
            EVENT_CALL_INCOMING,
            {
                "tg_call_id": tg_call_id,
                "user_id": user_id,
                "user_display": user_display,
                "outcome": call_store.OUTCOME_PENDING,
            },
        )
        self._enqueue(lambda: self._create_record(state, user_display))

    def call_started(self, tg_call_id: int, user_id: int) -> None:
        """Panggilan benar-benar aktif (media siap).

        `started_at` digeser ke waktu ini supaya `ended_at - started_at` sama
        dengan `duration_sec` yang diukur runtime (catatan Q12 di §5.5).
        """
        state = self._state(tg_call_id, user_id)
        started_at = utcnow()
        self._publish(
            EVENT_CALL_STARTED,
            {
                "tg_call_id": tg_call_id,
                "user_id": user_id,
                "record_id": state.record_id,
                "started_at": started_at.isoformat() + "Z",
            },
        )
        # Antrean FIFO: `_create_record` dijamin selesai lebih dulu, sehingga
        # `state.record_id` sudah terisi saat pekerjaan ini dijalankan.
        self._enqueue(lambda: self._mark_started(state, started_at))

    def call_ended(
        self,
        tg_call_id: int,
        user_id: int,
        *,
        outcome: str,
        end_reason: str | None = None,
        duration_sec: int | None = None,
    ) -> None:
        """Tutup panggilan: satu hook untuk dijawab, ditolak, maupun gagal."""
        state = self._states.get(tg_call_id) or self._state(tg_call_id, user_id)
        self._publish(
            EVENT_CALL_ENDED,
            {
                "tg_call_id": tg_call_id,
                "user_id": user_id,
                "record_id": state.record_id,
                "outcome": outcome,
                "end_reason": end_reason,
                "duration_sec": duration_sec,
            },
        )
        self._enqueue(lambda: self._finish_record(state, outcome, end_reason, duration_sec))

    def session_event(self, tg_call_id: int, event: str, data: dict[str, Any]) -> None:
        """Peristiwa sesi: `transcript` atau `tool_call`."""
        if event == EVENT_TRANSCRIPT:
            self._on_transcript(tg_call_id, data)
        elif event == EVENT_TOOL_CALL:
            self._on_tool_call(tg_call_id, data)

    # --------------------------------------------------------------- publikasi

    def _publish(self, event: str, data: dict[str, Any]) -> None:
        """Terbitkan ke bus (sinkron, tidak pernah melempar)."""
        if self._bus is None:
            return
        try:
            self._bus.publish(event, data)
        except Exception:  # noqa: BLE001 - pemantau tidak boleh mengganggu bot
            log.debug("Gagal menerbitkan event '%s'.", event, exc_info=True)

    # ----------------------------------------------------------------- handlers

    def _on_transcript(self, tg_call_id: int, data: dict[str, Any]) -> None:
        speaker = str(data.get("speaker") or call_store.SPEAKER_CALLER)
        text = self._redact(str(data.get("text") or "")).strip()
        if not text:
            return
        # `store_transcripts=false` mematikan penyimpanan maupun penyiaran teks.
        if not self._store_transcripts:
            return
        state = self._states.get(tg_call_id)
        if state is not None:
            state.tail.append({"speaker": speaker, "text": text})
            del state.tail[:-TRANSCRIPT_TAIL]
        self._publish(
            EVENT_TRANSCRIPT,
            {
                "tg_call_id": tg_call_id,
                "record_id": state.record_id if state is not None else None,
                "speaker": speaker,
                "text": text,
                "at": utcnow().isoformat() + "Z",
            },
        )
        self._enqueue(lambda: self._write_transcript(state, speaker, text))

    def _on_tool_call(self, tg_call_id: int, data: dict[str, Any]) -> None:
        name = str(data.get("name") or "")
        if not name:
            return
        args_json = call_store.dumps_json(self._redact_deep(data.get("args")))
        result_json = call_store.dumps_json(self._redact_deep(data.get("result")))
        status = str(data.get("status") or TOOL_STATUS_OK)
        duration_ms = int(data.get("duration_ms") or 0)
        state = self._states.get(tg_call_id)
        self._publish(
            EVENT_TOOL_CALL,
            {
                "tg_call_id": tg_call_id,
                "record_id": state.record_id if state is not None else None,
                "name": name,
                "status": status,
                "duration_ms": duration_ms,
            },
        )
        self._enqueue(
            lambda: self._write_tool_call(
                state, name, args_json, result_json, status, duration_ms
            )
        )

    # ------------------------------------------------------------------ writer

    def _state(self, tg_call_id: int, user_id: int) -> _CallState:
        state = self._states.get(tg_call_id)
        if state is None:
            state = _CallState(tg_call_id=tg_call_id, user_id=user_id)
            self._states[tg_call_id] = state
        return state

    def _enqueue(self, job: Callable[[], Any]) -> None:
        """Antukkan pekerjaan; buang bila penuh (audio tidak boleh menunggu)."""
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped % 100 == 1:
                log.warning(
                    "Antrean pencatatan panggilan penuh; %d pekerjaan dibuang.", self.dropped
                )

    async def _run_writer(self) -> None:
        """Task penulis tunggal: menjaga urutan tulis ke database."""
        while True:
            job = await self._queue.get()
            batch: list[Callable[[], Any] | None] = [job]
            stop = job is None
            while not stop and len(batch) < WRITE_BATCH:
                try:
                    extra = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                stop = extra is None
                batch.append(extra)
            for item in batch:
                if item is not None:
                    try:
                        await item()
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001 - kegagalan monitoring tak boleh fatal
                        log.exception("Gagal menyimpan data panggilan.")
            for _ in batch:
                self._queue.task_done()
            if stop:
                return

    # ------------------------------------------------------------------ writers

    async def _create_record(self, state: _CallState, user_display: str | None) -> None:
        state.record_id = await call_store.start_call(
            self._db,
            tg_call_id=state.tg_call_id,
            user_id=state.user_id,
            user_display=user_display,
        )

    async def _mark_started(self, state: _CallState, started_at: Any) -> None:
        if state.record_id is None:
            return
        await call_store.mark_call_started(self._db, state.record_id, started_at=started_at)

    async def _finish_record(
        self,
        state: _CallState,
        outcome: str,
        end_reason: str | None,
        duration_sec: int | None,
    ) -> None:
        self._states.pop(state.tg_call_id, None)
        if state.record_id is None:
            return
        await call_store.finish_call(
            self._db,
            state.record_id,
            outcome=outcome,
            end_reason=end_reason,
            duration_sec=duration_sec,
            transcript_count=state.transcript_count,
            tool_call_count=state.tool_call_count,
        )

    async def _write_transcript(self, state: _CallState | None, speaker: str, text: str) -> None:
        if state is None or state.record_id is None:
            return
        await call_store.add_transcript(
            self._db, state.record_id, speaker=speaker, text=text
        )
        state.transcript_count += 1
        await call_store.bump_call_counts(self._db, state.record_id, transcripts=1)

    async def _write_tool_call(
        self,
        state: _CallState | None,
        name: str,
        args_json: str | None,
        result_json: str | None,
        status: str,
        duration_ms: int,
    ) -> None:
        if state is None or state.record_id is None:
            return
        await call_store.add_tool_call(
            self._db,
            state.record_id,
            name=name,
            args_json=args_json,
            result_json=result_json,
            status=status,
            duration_ms=duration_ms,
        )
        state.tool_call_count += 1
        await call_store.bump_call_counts(self._db, state.record_id, tool_calls=1)

    # ---------------------------------------------------------------- redaksi

    def _redact(self, text: str) -> str:
        return self._redactor.redact(text) if self._redactor else text

    def _redact_deep(self, value: Any) -> Any:
        """Redaksi nilai tool (args/hasil) yang bisa berisi secret."""
        if self._redactor is None:
            return value
        if isinstance(value, str):
            return self._redactor.redact(value)
        if isinstance(value, dict):
            return {k: self._redact_deep(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._redact_deep(v) for v in value]
        return value

    # ------------------------------------------------------------------ status

    @property
    def db(self) -> Database:
        """Database tujuan penulisan (dipakai router untuk membaca terkait)."""
        return self._db

    @property
    def bus(self) -> EventBus | None:
        """Event bus tujuan penyiaran, bila ada."""
        return self._bus

    def record_id_for(self, tg_call_id: int) -> int | None:
        """Id `call_record` untuk panggilan yang sedang dipantau (atau `None`)."""
        state = self._states.get(tg_call_id)
        return state.record_id if state else None

    def transcript_tail(self, tg_call_id: int, limit: int = TRANSCRIPT_TAIL) -> list[dict[str, Any]]:
        """Transkrip terakhir (in-memory) untuk panggilan yang sedang berjalan."""
        state = self._states.get(tg_call_id)
        return list(state.tail[-limit:]) if state else []


async def build_recorder(
    db: Database,
    store: SettingsStore,
    *,
    bus: EventBus | None = None,
    redactor: SecretRedactor | None = None,
) -> CallRecorder:
    """Buat `CallRecorder` dan terapkan nilai awal `store_transcripts`."""
    recorder = CallRecorder(db, bus=bus, redactor=redactor)
    recorder.set_store_transcripts(bool(await store.get("store_transcripts")))
    recorder.start()
    return recorder