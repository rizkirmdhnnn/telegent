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

- [ ] **F1** API kontrol runtime (status/start/stop/restart/apply) — M
- [ ] **F2** UI kontrol runtime + indikator "butuh restart" + alur apply — M
- [ ] **F3** Pembersihan retensi (scheduler) — S

## Fase 5 — Hardening & rilis

- [ ] **G1** Packaging single-container (Docker multi-stage) + CLI `--no-web` + docs — L
- [ ] **H1** Test backend (API, auth, crypto, settings, runtime) — L
- [ ] **H2** Test frontend (unit + svelte-check) — M
- [ ] **H3** E2E Playwright + perluasan CI — L

---

## Checklist lintas-cutting

- [x] Redaksi secret di log & audit diuji khusus
- [x] Semua pesan error UI lewat kode i18n (id/en) — dijaga `tests/web/test_i18n_catalogs.py`
- [x] `uv run pytest -q` hijau
- [x] `uv run pyright src/telegent` hijau
- [x] `svelte-check` hijau
- [ ] Playwright hijau
- [x] `docs/web-panel` disinkronkan dengan implementasi
- [ ] README + dokumentasi deployment diperbarui
- [ ] Smoke test container bersih → panggilan nyata
