# TODO — Telegent Web Panel

Checklist eksekusi. Urutan mengikuti fase di [`plan.md`](plan.md). Setiap item
merujuk ke tiket detail di [`tickets/`](tickets/).

Legenda: `[ ]` belum · `[~]` dikerjakan · `[x]` selesai. Estimasi: S/M/L/XL.

---

## Fase 0 — Fondasi

> **Status: selesai** (branch `feat/web-panel-phase-0`). 206 tes hijau, pyright bersih.
> Endpoint `/api/settings` belum ada — itu tiket C1.

- [x] **A1** Skeleton web FastAPI + mount SPA + `healthz` + lifespan — M
- [x] **A2** Lapisan DB (SQLAlchemy async, SQLite WAL) + model + Alembic — L
- [x] **A3** Crypto secret (kunci file auto-generate, Fernet) — S
- [x] **A4** Settings registry + SettingsStore (DB ⇄ `Settings`, import `.env`) — L
- [x] **A5** Auth admin (password, cookie sesi, CSRF) + first-run setup + TOTP — L
- [x] **A6** Audit log (infra + masking secret) — S
- [x] **A7** Refactor `TelegentApp` + `RuntimeController` (start/stop/restart) — L
- [x] **A8** EventBus + logging handler SSE (redaksi, buffer) — M

## Fase 1 — Konfigurasi

> **Status: selesai + review diperbaiki.** Backend (pytest/pyright) dan frontend
> (svelte-check) hijau. `GET /api/runtime/status` dan `POST /api/runtime/apply`
> sengaja dibuat lebih dulu dari tiket F1 karena B3/C2 memerlukannya; kontrol
> start/stop/restart eksplisit tetap di F1.

- [x] **B1** Scaffold SvelteKit + shadcn-svelte + Tailwind + API client + i18n — L
- [x] **B2** UI auth: setup wizard, login, akun/TOTP — M
- [x] **B3** App shell: navigasi, layout, tema, ganti bahasa — M
- [x] **C1** API settings + endpoint schema — M
- [x] **C2** UI settings (form bergrup, validasi, badge hot/restart) — L
- [x] **C3** API kredensial + validasi, dan API tool — M
- [x] **C4** UI kredensial + UI tool — M

## Fase 2 — Login Telegram

> **Status: selesai + review diperbaiki** (branch `feat/web-panel-phase-2`). 320 tes hijau,
> pyright & svelte-check bersih. `telegram_login` dipecah menjadi tiga modul:
> `telegram_login` (orkestrasi klien), `telegram_store` (akses DB),
> `telegram_errors` (katalog kode galat). Login OTP + 2FA penuh dari panel, status
> akun, aksi "Ganti akun", logout, hitung mundur FloodWait, dan audit.
> `login/start` serta `logout` ditolak (`bot_running`) selama runtime berjalan.
> Tombol "Jalankan bot" memakai `POST /runtime/apply`; tombol start/stop eksplisit
> menunggu tiket F1/F2.

- [x] **D1** Layanan login Telegram programatik (send_code/verify/2FA, error) — L
- [x] **D2** API akun & login Telegram — M
- [x] **D3** UI login/akun Telegram (kode, password, status, hitung mundur) — M

## Fase 3 — Pemantauan

> **Status: selesai + review diperbaiki.** 439 tes hijau, pyright & svelte-check bersih.
> Satu penerbit event `call.*` (`CallRecorder`; `_emit_call` hanya jadi jalan keluar
> bila tidak ada observer), `started_at` digeser saat panggilan aktif, `record_id`
> ikut di semua event, `runtime.error` terbit, dan filter tanggal dikonversi ke UTC.

- [x] **E1** Hook persistensi: call record, transkrip, tool call — L
- [x] **E2** API pemantauan (aktif, riwayat, detail, hangup) — M
- [x] **E3** UI pemantauan (dashboard, daftar/detail panggilan, log live) — L

## Fase 4 — Kontrol & retensi

> **Status: F1 selesai.** Keputusan yang diambil:
> - `stop`/`restart` memakai **graceful drain** (bukan menolak 409): panggilan
>   aktif diberi `schedule_hangup`, ditunggu maks 10 detik, lalu dipaksa `close()`
>   bila masih hidup. Drain diuji di `test_runtime.py` & `test_runtime_control.py`.
> - Mode restart **in-process saja** pada fase ini; fallback container (Q4)
>   tidak dikerjakan — packaging container adalah Fase 5 (G1).
> - Pembersihan retensi (F3) memakai pola `retention_store.py`: satu siklus saat
>   boot lalu task harian (Q15); `audit_log` tidak pernah ikut terhapus.

- [x] **F1** API kontrol runtime (status/start/stop/restart/apply) — M
- [x] **F2** UI kontrol runtime + indikator "butuh restart" + alur apply — M
- [x] **F3** Pembersihan retensi (scheduler) — S

## Fase 5 — Hardening & rilis

> **Status: selesai + review diperbaiki** (branch `feat/web-panel-phase-5`).
> 702 tes pytest hijau (2 tes compose dilewati bila berkas compose-nya tak ada),
> pyright & svelte-check bersih, 76 tes Vitest hijau, 15 skenario Playwright
> hijau. Image Docker tunggal terbangun tanpa Node dan panel disajikan dari `/data`.
>
> Keputusan yang diambil:
> - **`TELEGENT_DATA_DIR` jadi satu sumber kebenaran** direktori data (sebelumnya
>   Docker memakai `TELEGRAM_SESSION_DIR`, panel memakai `TELEGENT_DATA_DIR`).
>   Alias lama tetap dibaca `Settings` untuk kompatibilitas, tapi compose/
>   `Dockerfile` hanya menyetel yang baru.
> - **Mode fake** (`telegent.web.fake`) hanya aktif lewat `TELEGENT_FAKE=1` yang
>   dibaca dari environment proses **sebelum** `load_dotenv`, sehingga `.env` yang
>   dibaca panel sendiri tidak menyalakannya. Peringatan mencolok + terlihat di
>   `/api/healthz`.
>   **Penting:** itu belum cukup. `env_file: .env` pada docker-compose menyalin isi
>   `.env` ke container tanpa melewati `load_dotenv`, jadi `TELEGENT_FAKE=1` yang
>   tertinggal di `.env` bisa menyalakan bot tiruan di produksi. Karena itu
>   compose **tidak** mendeklarasikan `TELEGENT_FAKE`, dan ada penjaga data nyata
>   (`fake.fake_blocked_reason`): bila `*.session` atau kredensial tersimpan sudah
>   ada, mode fake ditolak dengan pesan galat.
> - **`TELEGENT_IGNORE_DOTENV=1`** mematikan pembacaan `.env` sepenuhnya
>   (`load_dotenv` *dan* `Settings()`). Dipakai **E2E saja** (Playwright) agar
>   kredensial developer tidak ikut terimpor; container produksi justru relies
>   `.env` sebagai jalur migrasi dari deployment CLI.
> - **Tiga bug produksi ditemukan oleh tes Fase 5** dan diperbaiki:
>   `t(key, '')` membocorkan kunci mentah ke UI; `ThemeStore` melempar di
>   lingkungan tanpa `matchMedia`; dan `$state(new Set())` yang **tidak reaktif**
>   di Svelte 5 membuat tombol "Simpan Perubahan" selalu disabled.

- [x] **G1** Packaging single-container (Docker multi-stage) + CLI `--no-web` + docs — L
- [x] **H1** Test backend (API, auth, crypto, settings, runtime) — L
- [x] **H2** Test frontend (unit + svelte-check) — M
- [x] **H3** E2E Playwright + perluasan CI — L

---

## Checklist lintas-cutting

- [x] Redaksi secret di log & audit diuji khusus
- [x] Semua pesan error UI lewat kode i18n (id/en) — dijaga `tests/web/test_i18n_catalogs.py`
- [x] `uv run pytest -q` hijau
- [x] `uv run pyright src/telegent` hijau
- [x] `svelte-check` hijau
- [x] Playwright hijau
- [x] `docs/web-panel` disinkronkan dengan implementasi
- [x] README + dokumentasi deployment diperbarui
- [x] Smoke test container bersih → panel boot, DB + `.secret_key` terbentuk
- [ ] Smoke test panggilan nyata (butuh kredensial Telegram/Gemini asli).
      **Sudah berjalan di container** (2026-10-11) dan membongkar **tiga** bug
      nyata yang tidak pernah tertangkap tes:
      1. jalur **login** panel memicu prompt stdin (`Client.start()`),
      2. jalur **runtime bot** memicu prompt stdin untuk sesi yang ada tapi belum
         terotorisasi,
      3. `sign_in` dipanggil dengan argumen **terbalik** — kode OTP masuk ke slot
         `phone_code_hash`. Akibatnya Python melempar `TypeError` secara lokal,
         jadi kode yang benar pun **tidak pernah dikirim** ke Telegram; errornya
         dipetakan menjadi `telegram_error`.
      Ketiganya sudah diperbaiki dan diverifikasi ulang di container.
      Sisa: konfirmasi satu panggilan suara sungguhan dari nomor Telegram.
