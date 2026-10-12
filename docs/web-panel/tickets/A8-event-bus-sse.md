# A8 — EventBus + logging handler SSE

- **Epic/Fase:** A / Fase 0
- **Dependensi:** A1
- **Estimasi:** M
- **Referensi:** spec §7 · open-questions Q5

## Konteks
UI perlu aliran live (status, panggilan, transkrip, log). Ini fondasi transport
pub/sub in-process yang aman untuk banyak klien.

## Tujuan
- `EventBus`: `publish(event)`, `subscribe() -> AsyncIterator`, non-blocking.
- `LoggingHandler`: meneruskan `logging.Record` ke bus, dengan redaksi secret.
- Ring buffer log (`log_buffer_lines`) untuk dikirim saat klien baru tersambung.
- Tipe event sesuai spec §7.

## Deliverable
- `src/telegent/web/events.py`
- `src/telegent/web/log_stream.py`
- Modifikasi `src/telegent/logging_setup.py` untuk memasang handler (opsional).

## Langkah implementasi
1. Implementasi bus dengan `asyncio.Queue` per subscriber (bounded); drop saat penuh.
2. Definisikan dataclass event (status/call/transcript/tool/log/runtime.error).
3. `LoggingHandler.emit` → bentuk dict → `bus` (jangan memblok; abaikan bila penuh).
4. Redaksi: filter nilai secret yang dikenal (dari registry) sebelum publish.
5. Ring buffer untuk log terbaru.

## Kriteria terima (Definition of Done)
- [ ] Subscriber menerima event yang di-publish (tes async).
- [ ] Subscriber lambat tidak memblok penerbit (drop terukur).
- [ ] Nilai secret yang terdaftar tidak muncul di event log (tes).
- [ ] Klien baru menerima ring buffer log terakhir saat sambung.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q5 (satu vs dua endpoint stream) — diputuskan di tiket E3/logs.
