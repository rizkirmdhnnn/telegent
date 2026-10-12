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
- [x] `status` akurat dan berubah setelah start/stop.
- [x] `restart` idempoten & aman saat ada panggilan aktif (kebijakan drain/force jelas).
- [x] `apply` menghapus status `pending_restart`.
- [x] Aksi `stop`/`restart` tidak mematikan web.
- [x] Audit tercatat (sukses & gagal, dengan actor + IP).
- [x] Tes status + start/stop (fake).
- [x] `pyright` hijau.

## Catatan teknis / pertanyaan
- **Keputusan F1 (drain):** `stop`/`restart` mengakhiri panggilan aktif secara
  graceful alih-alih menolak dengan 409. Kontrak ini mengikat; mengubahnya berarti
  mengubah `tests/web/test_runtime.py::test_stop_mendrain_panggilan_aktif` dan
  `tests/web/test_runtime_control.py::test_stop_mengakhiri_panggilan_aktif_secara_graceful`.
- **Q4 (fallback restart container)** diputuskan: fase ini tetap in-process saja;
  fallback container tidak ada. Alasan: packaging container adalah Fase 5 (G1).
