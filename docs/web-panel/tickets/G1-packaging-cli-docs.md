# G1 — Packaging single-container + CLI `--no-web` + dokumentasi

- **Epic/Fase:** G / Fase 5
- **Dependensi:** hampir seluruh fitur (A–F)
- **Estimasi:** L
- **Referensi:** plan §2, §6, §11 · spec §3

## Konteks
Agar dapat dipakai self-host dengan `docker compose up`, perlu packaging satu
container (build SPA + runtime Python + volume `data/`) dan penyesuaian entry CLI.

## Tujuan
- Dockerfile multi-stage: stage Node untuk build SPA → stage Python menjalankan web+bot.
- `docker-compose.yml`: satu service, volume `./data`, env bootstrap.
- `telegent` menjalankan web+bot; `--no-web` untuk headless (testing/CI).
- Dokumentasi deployment & keamanan diperbarui.

## Deliverable
- `Dockerfile` (multi-stage)
- `docker-compose.yml` (diperbarui)
- `pyproject.toml` (dependensi web; opsional extra `web`)
- `src/telegent/__main__.py` (mode default web+bot, flag `--no-web`, `--host`, `--port`)
- `README.md` + `docs/web-panel/` (panduan deploy, security notes)

## Langkah implementasi
1. Dockerfile: build `frontend/` (Node) → salin `build/` ke image Python → install paket.
2. Entry CLI: `main()` memulai `uvicorn` (create_app) yang di lifespan-nya menjalankan
   `RuntimeController` (bila `TELEGENT_AUTOSTART_BOT` & akun siap). `--no-web` → jalankan
   `TelegentApp.run()` seperti sekarang (tanpa web).
3. Compose: `TELEGENT_HOST`, `TELEGENT_PORT`, volume `./data:/data`, restart policy.
4. Dokumentasi: cara akses via tunnel/VPN, backup `data/` (DB + `.secret_key` + `*.session`),
   peringatan tanpa TLS, migrasi dari deployment `.env` lama.

## Kriteria terima (Definition of Done)
- [x] `docker compose up` → panel tersedia di host:port; bot mulai bila akun siap.
- [x] `telegent --no-web` berperilaku seperti deployment lama (headless).
- [x] Volume `data/` mempertahankan DB, secret key, dan sesi antar restart.
- [x] Build menghasilkan image tunggal tanpa langkah manual Node di host.
- [x] Dokumentasi deploy & keamanan lengkap dan akurat.
- [x] `uv run pytest -q` & `pyright` hijau (paket tetap konsisten).

## Catatan teknis / pertanyaan
- Q16 (bind default 127.0.0.1), Q18 (nama produk "Telegent"), Q19 (tanpa telemetri).
