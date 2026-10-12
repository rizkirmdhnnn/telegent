# Telegent Web Panel — Dokumentasi Perencanaan

Panel admin berbasis web untuk **Telegent**: memindahkan seluruh operasional yang
kini murni CLI/`.env` (kredensial, konfigurasi, login akun Telegram, pemantauan
panggilan, log, kontrol proses) ke satu antarmuka web.

> Status dokumen: **Draft — siap ditinjau, belum diimplementasikan.**
> Versi basis kode: `telegent 0.2.0`.

## Isi dokumen

| Berkas | Isi |
|---|---|
| [`plan.md`](plan.md) | Visi, arsitektur target, fase, risiko, NFR, dampak refactor. |
| [`spec.md`](spec.md) | Spesifikasi fungsional & teknis: model data, registry setting, API REST, alur, SSE, keamanan. |
| [`todos.md`](todos.md) | Checklist eksekusi (dikelompokkan per epic & fase). |
| [`tickets/README.md`](tickets/README.md) | Indeks tiket + template tiket + peta dependensi. |
| [`tickets/`](tickets/) | Satu berkas per tiket (konteks, kriteria terima, langkah, dependensi, estimasi). |
| [`open-questions.md`](open-questions.md) | Keputusan yang sudah diambil dan pertanyaan yang masih terbuka. |

## Ringkasan keputusan (hasil grilling)

**Produk & model**
- **Single-tenant**, self-host, **satu pemilik/admin**.
- **Satu akun Telegram aktif** per deployment.
- Cakupan v1 **lengkap**: konfigurasi + login Telegram via web + pemantauan + kontrol proses.
- **Dwibahasa (Indonesia/Inggris)** dengan i18n; default Indonesia.

**Arsitektur**
- **Monolit 1 proses**: FastAPI menyajikan UI/API **dan** menjalankan `TelegentApp`
  di event loop yang sama → satu container.
- Frontend **SPA Svelte + shadcn-svelte**, di-build statis lalu dilayani FastAPI.
- Komunikasi: **REST untuk CRUD**, **SSE untuk aliran live** (status, panggilan, log, transkrip).
- **SQLite** via SQLAlchemy async + Alembic.
- **DB = sumber kebenaran** konfigurasi; `.env` hanya bootstrap (path DB, host/port, dll).
- **Secret terenkripsi at-rest** (Fernet); kunci auto-generate ke `data/.secret_key`
  (chmod 600), dapat di-override via env.
- Penerapan perubahan: **live-apply** untuk setting yang mendukung, **restart runtime
  in-process** untuk kredensial/akun (web tetap hidup).
- Akses **privat** (VPN/SSH tunnel), tanpa reverse proxy/TLS bawaan.
- `telegent` menjalankan web+bot secara default; tersedia **mode headless** (`--no-web`)
  untuk testing/CI.
- Tool: **toggle tool bawaan + parameter** (tanpa tool kustom via web).

**Observability & kualitas**
- **Riwayat panggilan + transkrip + tool call persisten**, retensi dapat diatur.
- Testing: **pytest + pyright + svelte-check + Playwright e2e**; CI diperluas.

## Cara membaca

1. Mulai dari [`plan.md`](plan.md) untuk gambaran & keputusan besar.
2. Lanjut [`spec.md`](spec.md) untuk detail teknis (kontrak API & skema).
3. Eksekusi mengikuti [`todos.md`](todos.md) dan [`tickets/`](tickets/).
4. Cek [`open-questions.md`](open-questions.md) sebelum mulai — ada beberapa
   keputusan tingkat-tiket yang perlu dikonfirmasi.

## Konvensi tiket

- Prefix family: `A` fondasi · `B` shell frontend · `C` konfigurasi & kredensial ·
  `D` login Telegram · `E` pemantauan · `F` kontrol runtime · `G` packaging & docs ·
  `H` kualitas.
- Estimasi: **S** (≤0,5 hari) · **M** (1–2 hari) · **L** (3–5 hari) · **XL** (>5 hari).
- Setiap tiket punya **Definition of Done** yang eksplisit (termasuk test/typecheck).
