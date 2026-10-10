# TODO — Telegent Web Panel

Checklist eksekusi. Urutan mengikuti fase di [`plan.md`](plan.md). Setiap item
merujuk ke tiket detail di [`tickets/`](tickets/).

Legenda: `[ ]` belum · `[~]` dikerjakan · `[x]` selesai. Estimasi: S/M/L/XL.

---

## Fase 0 — Fondasi

- [x] **A1** Skeleton web FastAPI + mount SPA + `healthz` + lifespan — M
- [x] **A2** Lapisan DB (SQLAlchemy async, SQLite WAL) + model + Alembic — L
- [x] **A3** Crypto secret (kunci file auto-generate, Fernet) — S
- [x] **A4** Settings registry + SettingsStore (DB ⇄ `Settings`, import `.env`) — L
- [x] **A5** Auth admin (password, cookie sesi, CSRF) + first-run setup + TOTP — L
- [x] **A6** Audit log (infra + masking secret) — S
- [x] **A7** Refactor `TelegentApp` + `RuntimeController` (start/stop/restart) — L
- [ ] **A8** EventBus + logging handler SSE (redaksi, buffer) — M

## Fase 1 — Konfigurasi

- [ ] **B1** Scaffold SvelteKit + shadcn-svelte + Tailwind + API client + i18n — L
- [ ] **B2** UI auth: setup wizard, login, akun/TOTP — M
- [ ] **B3** App shell: navigasi, layout, tema, ganti bahasa — M
- [ ] **C1** API settings + endpoint schema — M
- [ ] **C2** UI settings (form bergrup, validasi, badge hot/restart) — L
- [ ] **C3** API kredensial + validasi, dan API tool — M
- [ ] **C4** UI kredensial + UI tool — M

## Fase 2 — Login Telegram

- [ ] **D1** Layanan login Telegram programatik (send_code/verify/2FA, error) — L
- [ ] **D2** API akun & login Telegram — M
- [ ] **D3** UI login/akun Telegram (kode, password, status, hitung mundur) — M

## Fase 3 — Pemantauan

- [ ] **E1** Hook persistensi: call record, transkrip, tool call — L
- [ ] **E2** API pemantauan (aktif, riwayat, detail, hangup) — M
- [ ] **E3** UI pemantauan (dashboard, daftar/detail panggilan, log live) — L

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

- [ ] Redaksi secret di log & audit diuji khusus
- [ ] Semua pesan error UI lewat kode i18n (id/en)
- [ ] `uv run pytest -q` hijau
- [ ] `uv run pyright src/telegent` hijau
- [ ] `svelte-check` hijau
- [ ] Playwright hijau
- [ ] `docs/web-panel` disinkronkan dengan implementasi
- [ ] README + dokumentasi deployment diperbarui
- [ ] Smoke test container bersih → panggilan nyata
