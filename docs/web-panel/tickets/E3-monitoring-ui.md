# E3 — UI pemantauan: dashboard, panggilan, log live

- **Epic/Fase:** E / Fase 3
- **Dependensi:** E2, A8, B3
- **Estimasi:** L
- **Referensi:** spec §6.8, §7, §8.5 · open-questions Q14

## Konteks
Bagian inti "full website" adalah memantau bot secara live dan menelusuri panggilan
beserta transkrip/log — menggantikan `docker compose logs -f`.

## Tujuan
- Dashboard: status runtime, jumlah panggilan aktif, aktivitas terbaru.
- Daftar & detail panggilan (dengan transkrip + tool call), ekspor CSV (Q14).
- Halaman log live dengan tingkat, pencarian, dan pause/auto-scroll.

## Deliverable
- `frontend/src/routes/(app)/+page.svelte` (dashboard)
- `frontend/src/routes/(app)/calls/+page.svelte` + `[id]/+page.svelte`
- `frontend/src/routes/(app)/logs/+page.svelte`
- Utilitas SSE (`EventSource` wrapper + reconnect)

## Langkah implementasi
1. SSE wrapper: sambung `/api/events/stream` & `/api/logs/stream`, auto-reconnect +
   backoff, `EventSource` bawaan.
2. Dashboard: kartu status + tabel panggilan aktif (update live) + feed aktivitas.
3. Calls: tabel riwayat (filter/paginasi), halaman detail menampilkan transkrip
   (bubble caller/AI) & tool call (tabel), tombol hangup untuk yang aktif, ekspor CSV.
4. Logs: virtualized list (batas `log_buffer_lines`), filter level & teks, tombol
   pause/clear, indikator koneksi.

## Kriteria terima (Definition of Done)
- [ ] Status & panggilan aktif ter-update live tanpa refresh.
- [ ] Transkrip & tool call tampil benar dengan urutan waktu.
- [ ] Ekspor CSV mengunduh data sesuai filter.
- [ ] Log live mengalir, dapat dijeda/di-filter; reconnect saat koneksi putus.
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Q14 (ekspor CSV), Q5 (dua endpoint stream).
