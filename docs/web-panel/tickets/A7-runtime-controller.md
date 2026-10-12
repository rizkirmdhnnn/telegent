# A7 — Refactor TelegentApp + RuntimeController

- **Epic/Fase:** A / Fase 0
- **Dependensi:** A1, A4
- **Estimasi:** L
- **Referensi:** plan §10 · spec §8.6 · open-questions Q4

## Konteks
`TelegentApp.run()` saat ini memblok sampai shutdown dan membuat klien sendiri.
Agar web bisa start/stop/restart tanpa mematikan panel, perlu seam lifecycle.

## Tujuan
- `TelegentApp` dapat dikonstruksi & dijalankan sebagai task tanpa `asyncio.run`.
- `RuntimeController`: `start()`, `stop()`, `restart()`, `status()`, idempoten & aman
  dari konkurensi (lock).
- Menerima `Settings` terbaru dari `SettingsStore` (hot-apply untuk panggilan baru).

## Deliverable
- Modifikasi `src/telegent/app.py` (pisahkan `start()`/`_run()`/`_shutdown()`;
  `settings` dapat diganti; hook event ke A8 — interface saja di sini).
- `src/telegent/web/runtime.py` (`RuntimeController`)

## Langkah implementasi
1. Pisah `run()` menjadi `start()` (bangun klien + task) dan `wait()`/`_stop` (dengan
   `async run()` tetap ada untuk headless, memanggil keduanya).
2. Tambah `set_settings(new)` pada `TelegentApp` (dipakai panggilan baru).
3. `RuntimeController`:
   - `start()`: bila belum login/kredensial → kembalikan status, jangan error keras.
   - `stop()`: set `_stop`, tunggu `_shutdown` selesai (dengan timeout).
   - `restart()`: `stop()` lalu `start()` di bawah `asyncio.Lock`.
   - `status()`: running/state/since/model/active_calls/logged_in_user/last_error.
4. Tangkap error konstruksi klien (kredensial/sesi) → simpan `last_error` (tanpa secret).
5. Mode fallback (Q4): flag `runtime_restart_mode = in_process|container` (opsional).

## Kriteria terima (Definition of Done)
- [ ] `telegent` (headless) tetap berperilaku sama seperti sebelum refactor.
- [ ] `start/stop/restart` berulang tidak membocorkan task/klien (uji 5 siklus).
- [ ] Bila kredensial belum ada, `start()` mengembalikan `not_configured` tanpa crash.
- [ ] `settings` baru terpakai panggilan berikutnya.
- [ ] Smoke test: start → terima panggilan (fake/local) → stop.
- [ ] `pyright` + pytest lama tetap hijau.

## Catatan teknis / pertanyaan
- Q4 (fallback restart container).
