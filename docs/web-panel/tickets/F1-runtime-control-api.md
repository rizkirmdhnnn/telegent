# F1 — API kontrol runtime

- **Epic/Fase:** F / Fase 4
- **Dependensi:** A7, A4, A6
- **Estimasi:** M
- **Referensi:** spec §6.5, §8.6

## Konteks
Admin perlu menjalankan, menghentikan, me-restart bot, dan menerapkan perubahan
konfigurasi yang butuh restart — semuanya dari web.

## Tujuan
- `GET /runtime/status`
- `POST /runtime/start`, `/stop`, `/restart`, `/apply`
- Semua aksi tercatat di audit.

## Deliverable
- `src/telegent/web/routers/runtime.py`

## Langkah implementasi
1. `status`: dari `RuntimeController.status()` (running/state/since/model/active_calls/
   logged_in_user/last_error).
2. `start`: panggil `RuntimeController.start()`; bila belum login/kredensial → kembalikan
   status terkait (bukan error 500).
3. `stop`: hentikan dengan drain singkat (beri tahu jumlah sesi aktif).
4. `restart`: ulang penuh (in-process); `apply`: sama dengan restart, dipicu setelah
   perubahan `restart` (semantik: bersihkan `pending_restart`).
5. Audit untuk start/stop/restart/apply.

## Kriteria terima (Definition of Done)
- [ ] `status` akurat dan berubah setelah start/stop.
- [ ] `restart` idempoten & aman saat ada panggilan aktif (kebijakan drain/force jelas).
- [ ] `apply` menghapus status `pending_restart`.
- [ ] Aksi `stop`/`restart` tidak mematikan web.
- [ ] Audit tercatat.
- [ ] Tes status + start/stop (fake).
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q4 (fallback restart container) bila in-process bermasalah.
