# Keputusan & Pertanyaan Terbuka — Telegent Web Panel

## A. Keputusan yang sudah final (hasil grilling)

| # | Topik | Keputusan |
|---|---|---|
| 1 | Model kepemilikan | Single-tenant, self-host, satu pemilik/admin. |
| 2 | Topologi runtime | Monolit 1 proses (FastAPI + bot se-event-loop), satu container. |
| 3 | Stack UI | SPA **Svelte + shadcn-svelte**. |
| 4 | Sumber konfigurasi | **DB = sumber kebenaran**; `.env` hanya bootstrap; secret terenkripsi. |
| 5 | Database | **SQLite** via SQLAlchemy async (+ Alembic). |
| 6 | Auth | Akun admin tunggal + password + **TOTP opsional**; cookie sesi + CSRF. |
| 7 | Cakupan v1 | Lengkap: config + login web + monitoring + kontrol proses. |
| 8 | Jumlah akun Telegram | **Satu akun aktif**. |
| 9 | Penerapan perubahan | **Live-apply** + **restart runtime in-process**. |
| 10 | Deployment/eksposur | Satu container, akses **privat** (VPN/tunnel), tanpa reverse proxy/TLS. |
| 11 | Observability | Riwayat + transkrip + tool call persisten; retensi dapat diatur. |
| 12 | Tool | Toggle tool bawaan + parameter (tanpa tool kustom). |
| 13 | Peran CLI | `telegent` = web+bot default; mode headless `--no-web` untuk testing. |
| 14 | Bahasa & tema | Dwibahasa (id/en, default id) + mode terang/gelap. |
| 15 | Kanal real-time | **SSE** (live) + **REST** (CRUD). |
| 16 | Kunci enkripsi | Auto-generate ke `data/.secret_key` (chmod 600); override via env. |
| 17 | Testing | Backend (pytest) + frontend (svelte-check + unit) + e2e Playwright + CI. |
| 18 | Deliverable | Docs markdown terstruktur di `docs/web-panel/`. |

## B. Pertanyaan terbuka (perlu diputuskan sebelum/ketika tiket terkait dikerjakan)

Ditandai `Qn` dan direferensikan di tiket. **Default rekomendasi** dicantumkan;
bila tidak dikoreksi, implementasi memakai default.

- **Q1 (A2): Mode DB.** WAL mode SQLite + `busy_timeout`. Rekomendasi: aktifkan WAL dan
  satu engine async; tulis dari bot & web lewat engine yang sama. *Default: ya.*
- **Q2 (A5): Algoritma hash.** Rekomendasi: `argon2` (paket `argon2-cffi`); fallback
  `bcrypt` bila dependensi ditolak. *Default: argon2.*
- **Q3 (A5): Lockout.** Ambang & durasi? Rekomendasi: 5 percobaan gagal → lockout 15 menit
  (naik bertahap). *Default: 5 / 15 menit.*
- **Q4 (A7): Restart in-process vs fallback container.** ~~ Bila restart klien
  in-process terbukti tidak stabil, apakah boleh fallback ke restart container? ~~
  **Diputuskan (Fase 4 / F1): tetap in-process saja.** Tidak ada mode container
  pada fase ini; packaging container adalah G1 (Fase 5). Restart in-process
  diserialisasi dengan `asyncio.Lock` dan selalu aman terhadap klik ganda.
- **Q5 (A8): Kombinasi stream.** Satu endpoint `/events/stream` untuk semua (status/panggilan/
  transkrip) + `/logs/stream` terpisah. *Default: ya (dua endpoint).*
- **Q6 (B1): SvelteKit vs Vite SPA.** Rekomendasi: **SvelteKit dengan `adapter-static`**
  (SPA mode, routing file-based). *Default: SvelteKit static.*
- **Q7 (B1): Versi Svelte.** Rekomendasi: Svelte 5 (runes) + shadcn-svelte versi yang
  kompatibel. *Default: Svelte 5.*
- **Q8 (C1): Format value `allowed_user_ids`.** Simpan sebagai `list[int]` di DB, render
  sebagai chip/tag di UI. *Default: list[int].*
- **Q9 (C2): Field audio lanjutan.** Tampilkan sebagai seksi "Advanced" yang bisa
  dibuka-tutup, atau sembunyikan sepenuhnya dari UI? *Default: seksi Advanced, read-only
  pada v1.*
- **Q10 (D1): Penyimpanan sesi Telegram.** Direktori sesi tetap `TELEGENT_DATA_DIR`
  (mount `data/`). Ganti nama sesi = buat sesi baru (tak memindahkan berkas). *Default: ya.*
- **Q11 (D1): Dukungan 2FA saat login.** Wajib didukung (banyak akun memakainya). *Default: ya.*
- **Q12 (E1): Kapan `call_record` dibuat.** Saat panggilan **diterima** (ACTIVE) atau
  saat **masuk** (termasuk penolakan)? Rekomendasi: buat saat masuk agar penolakan
  (whitelist/rate-limit/kapasitas) tercatat. *Default: saat masuk.*
- **Q13 (E1): Simpan transkrip default.** `store_transcripts=true`; dapat dimatikan untuk
  privasi. *Default: true.*
- **Q14 (E3): Export riwayat.** Sediakan ekspor CSV/JSON? *Default: v1 sertakan ekspor CSV.*
- **Q15 (F3): Jadwal pembersihan retensi.** Harian saat idle (mis. 03:00 lokal) + saat boot.
  *Default: harian.*
- **Q16 (G1): Port default & bind.** `127.0.0.1:8080`. Untuk akses perangkat lain di LAN,
  set `TELEGENT_HOST=0.0.0.0` secara sadar. *Default: 127.0.0.1.*
- **Q17 (H3): E2E tanpa Telegram/Gemini nyata.** Gunakan mode fake (fake live session &
  fake telegram) agar CI deterministik. *Default: ya, fake.*
- **Q18 (Umum): Nama produk panel.** Tetap "Telegent" di UI, atau beri nama panel
  (mis. "Telegent Console")? *Default: "Telegent".*
- **Q19 (Umum): Telemetri/analytics panel.** Rekomendasi: tidak ada telemetri keluar
  (privasi self-host). *Default: tidak ada.*
- **Q20 (A4): Perilaku env→DB saat upgrade.** Bila env berubah setelah import awal,
  apakah env menimpa DB? *Default: tidak — DB menang setelah import pertama; env hanya
  untuk key yang belum ada di DB.*

## C. Asumsi yang dipakai bila tidak dikoreksi

- Python ≥ 3.10; Node ≥ 20 untuk build SPA (hanya saat build Docker/CI).
- Satu admin; tidak ada manajemen pengguna tambahan.
- Tanpa multi-akun Telegram; ganti akun = logout + login.
- Riwayat audio tidak disimpan (hanya transkrip teks).
