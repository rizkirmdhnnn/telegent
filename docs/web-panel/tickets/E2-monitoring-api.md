# E2 — API pemantauan

- **Epic/Fase:** E / Fase 3
- **Dependensi:** E1, A5
- **Estimasi:** M
- **Referensi:** spec §6.6

## Konteks
UI butuh data panggilan aktif, riwayat, detail + transkrip, dan aksi mengakhiri
panggilan.

## Tujuan
- `GET /calls/active` (dari `RuntimeController.sessions`).
- `GET /calls` (riwayat, paginasi & filter).
- `GET /calls/{id}`, `/transcript`, `/tools`.
- `POST /calls/{id}/hangup`.

## Deliverable
- `src/telegent/web/routers/calls.py`
- Skema & query paginasi

## Langkah implementasi
1. `active`: petakan sesi runtime → `{user_id, call_id, state, duration, transcript_tail}`.
2. `calls`: query `call_record` dengan filter (`from`, `to`, `user`, `outcome`) +
   paginasi; sertakan ringkasan (durasi, counts).
3. `{id}`: detail record; `transcript` & `tools`: daftar terkait.
4. `hangup`: panggil `CallSession.schedule_hangup()` untuk sesi aktif (validasi call_id).
5. Audit untuk `hangup`.

## Kriteria terima (Definition of Done)
- [ ] Daftar panggilan aktif akurat & real-time-ish (fallback poll + SSE).
- [ ] Riwayat ter-paginasi, filter bekerja, total benar.
- [ ] Detail menampilkan transkrip & tool call berurutan waktu.
- [ ] `hangup` benar-benar mengakhiri panggilan (fake) & tercatat audit.
- [ ] Tes query/paginasi & hangup.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q14 (ekspor CSV) diselesaikan di E2/E3.
