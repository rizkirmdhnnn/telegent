# Rencana — Telegent Web Panel

> Status: Draft · Basis: `telegent 0.2.0` · Konteks: single-tenant, self-host.

## 1. Latar belakang

Saat ini Telegent dioperasikan sepenuhnya lewat CLI dan file `.env`:

- Setup manual: `uv sync` → `cp .env.example .env` → mengisi kredensial dengan editor teks.
- Login akun Telegram bersifat **interaktif di terminal** (nomor → OTP → password 2FA).
- Konfigurasi runtime hanya lewat variabel env (whitelist, batas beban, persona, model,
  anti-idle, level log); sebagian flag lewat `--allow-user`/`--log-level`.
- Tanpa jalur untuk mengubah konfigurasi saat proses berjalan (harus edit file + restart).
- Pemantauan hanya lewat `docker compose logs -f`; tidak ada riwayat panggilan/transkrip.
- Tidak ada autentikasi terpusat maupun audit perubahan.

Tujuan fitur: **menyediakan layanan website** tempat admin/pemilik mengkonfigurasi seluruh
platform, memantau, dan mengendalikan proses — menghapus ketergantungan pada CLI.

## 2. Tujuan & metrik sukses

**Tujuan**
1. Semua pengaturan yang sebelumnya di `.env` dapat dikelola dari web (dengan validasi).
2. Login & pengelolaan akun Telegram dilakukan dari web (tanpa terminal interaktif).
3. Pemantauan real-time: status bot, panggilan aktif, riwayat, transkrip, tool call, log.
4. Kontrol proses: start/stop/restart dan terapkan perubahan dari web.
5. Keamanan: satu akun admin terautentikasi, secret terenkripsi, audit perubahan.

**Metrik sukses (v1)**
- Setup dari nol → bot siap menerima panggilan **tanpa menyentuh terminal** selain
  `docker compose up`.
- Semua field `.env.example` (kecuali bootstrap) memiliki padanan UI yang tervalidasi.
- Perubahan setting non-kredensial berlaku **tanpa** mematikan web.
- Riwayat panggilan + transkrip dapat ditelusuri dan diekspor dari UI.
- CI hijau: pytest + pyright + svelte-check + Playwright.

## 3. Prinsip desain

- **Satu proses, satu container** — minimalkan moving parts untuk self-host.
- **DB = sumber kebenaran** — `.env` hanya bootstrap; runtime membaca dari store.
- **Fail-fast & tervalidasi** — setiap setting divalidasi dengan tipe/aturan sebelum disimpan.
- **Aman secara default** — secret terenkripsi, cookie httpOnly, CSRF, audit.
- **Seam untuk testability** — runtime controller & event bus dapat diuji dengan fake,
  meneruskan pola `protocols.AudioSink`/`LiveVoiceSession` yang sudah ada.
- **Perubahan bertahap & ter-reversibel** — pisahkan `hot` vs `restart` dengan jelas di UI.
- **i18n sejak awal** — semua teks UI lewat lapisan terjemahan.

## 4. Ruang lingkup

**Termasuk (v1)**
- Autentikasi admin + first-run setup wizard.
- Manajemen kredensial Telegram (api_id/api_hash) & Gemini (API key), tervalidasi & terenkripsi.
- Login akun Telegram via web (kode + password 2FA), status akun, logout/ganti akun.
- Editor konfigurasi lengkap (kebijakan akses/beban, persona/prompt, model, anti-idle, log, tool).
- Manajemen tool bawaan (toggle + parameter).
- Pemantauan: dashboard status, panggilan aktif, riwayat, detail + transkrip, log live (SSE).
- Kontrol runtime: start/stop/restart, indikator "butuh restart", terapkan perubahan.
- Retensi data (pembersihan otomatis).
- Audit log perubahan konfigurasi & aksi administratif.
- Packaging single-container + mode headless untuk CI.

**Di luar cakupan (v1)**
- Multi-tenant / banyak akun Telegram paralel.
- Billing/langganan.
- Tool kustom via web (eksekusi kode/HTTP webhook).
- Reverse proxy/TLS bawaan (akses diasumsikan privat).
- Recording audio panggilan (hanya transkrip teks).
- Manajemen beberapa admin/RBAC granular.

## 5. Keputusan arsitektur (ringkas)

| # | Keputusan | Alasan | Konsekuensi |
|---|---|---|---|
| ADR-1 | Monolit 1 proses (FastAPI + bot se-loop) | Akses langsung ke `sessions`/tools/status, hot-config, satu container | Perlu refactor `TelegentApp` agar embeddable; restart klien in-process |
| ADR-2 | SPA Svelte + shadcn dilayani FastAPI | UX modern, tanpa server-render template | Tambah toolchain Node saat build (multi-stage) |
| ADR-3 | REST + SSE | Sederhana, satu arah cukup untuk aliran live | Kontrol lewat REST (bukan WS) |
| ADR-4 | SQLite + SQLAlchemy async | Zero-ops self-host | Butuh Alembic untuk migrasi |
| ADR-5 | DB sumber kebenaran, `.env` bootstrap | Hot-config + audit + validasi | Perlu migrasi `.env` → DB saat pertama |
| ADR-6 | Secret terenkripsi (Fernet), kunci file auto-generate | Aman tanpa langkah CLI | Kunci harus bertahan di volume `data/` |
| ADR-7 | Live-apply + restart in-process | Web tetap hidup, UX mulus | Perlu bedah lifecycle klien Telegram/ntgcalls/Gemini |
| ADR-8 | Satu akun Telegram aktif | Sederhana, sesuai desain sekarang | Ganti akun = logout + login ulang |
| ADR-9 | Tool: toggle + parameter | Aman, tanpa eksekusi kode dari web | Tool baru tetap lewat kode |
| ADR-10 | Observability persisten + retensi | Riwayat/transkrip dapat ditelusuri | Perlu hook dari `CallSession` |
| ADR-11 | Akses privat (VPN/tunnel) | Aman & sederhana | Tanpa TLS; cookie tidak `Secure` |

## 6. Arsitektur target

```
                        ┌──────────────────────────── Browser (admin) ────────────────────────────┐
                        │  SPA Svelte + shadcn-svelte (dilayani statis oleh FastAPI)              │
                        │  REST (CRUD)  ·  SSE (status/panggilan/log/transkrip)                    │
                        └───────────────────────────────┬────────────────────────────────────────┘
                                                        │ HTTP (127.0.0.1 / jaringan privat)
┌───────────────────────────── Satu proses / satu container ─────────────────────────────┐
│                                                                                        │
│  FastAPI                                                                               │
│    ├─ Routers: auth · setup · settings · credentials · telegram · runtime ·            │
│    │            calls · tools · logs(SSE) · audit · healthz                            │
│    ├─ Security: password hash · session cookie · CSRF · TOTP                           │
│    ├─ Crypto: Fernet (kunci di data/.secret_key)                                       │
│    └─ RuntimeController ── masuk/kendali ─┐                                             │
│                                           │                                            │
│  ┌───────────── TelegentApp (runtime bot, event loop sama) ──────────────┐             │
│  │  Pyrogram Client  ·  ntgcalls  ·  Gemini Live  ·  CallSession[]        │             │
│  │  ToolRegistry     ·  CallRateLimiter                                   │             │
│  └───────────────┬───────────────────────────┬───────────────────────────┘             │
│                  │ publish event              │ baca setting                             │
│           ┌──────▼───────┐             ┌───────▼──────────┐                             │
│           │  EventBus    │             │  SettingsStore   │◀── DB (SQLite)              │
│           │ (log/call/…) │────────────▶│ (DB → Settings)  │   Orchestration/Config/Calls │
│           └──────────────┘             └──────────────────┘                             │
│                                                                                        │
│  SQLite (data/telegent.db) · Secret terenkripsi · Session *.session (data/)             │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Model deployment:** satu container (multi-stage: build SPA Node → runtime Python),
volume `./data` untuk DB, `*.session`, dan `.secret_key`.

## 7. Fase & milestone

| Fase | Fokus | Epic terkait | Milestone (demo) |
|---|---|---|---|
| **0. Fondasi** | Skeleton web, DB, crypto, settings store, auth, runtime controller, event bus | A | Bot jalan via web; login admin; ubah 1 setting dari UI |
| **1. Konfigurasi** | Settings/credentials/tools API + UI | B, C | Semua setting `.env` dapat diubah & tervalidasi dari UI |
| **2. Login Telegram** | Alur OTP/2FA via web + status akun | D | Login akun Telegram dari web, bot menerima panggilan |
| **3. Pemantauan** | Persistensi + dashboard/calls/logs + SSE | E | Lihat panggilan aktif, riwayat, transkrip, log live |
| **4. Kontrol & retensi** | start/stop/restart/apply + pembersihan data | F | Kontrol penuh proses & indikator restart dari UI |
| **5. Hardening & rilis** | Packaging, CLI, i18n, audit, TOTP, docs, CI/e2e | G, H | Siap rilis v0.3.0 |

## 8. Non-functional requirements

**Keamanan**
- Satu akun admin; password di-hash (argon2/bcrypt).
- Session cookie `httpOnly`, `SameSite=Lax`, TTL dapat diatur; CSRF token pada mutasi.
- Secret (api_hash, API key) **selalu** disimpan terenkripsi; UI menampilkan versi tersamar.
- Rate-limit & lockout login; opsi TOTP 2FA.
- Semua perubahan konfigurasi & aksi (restart/logout) tercatat di audit log.
- Tidak melakukan logging nilai secret (redaksi di log handler & error).

**Performa & reliabilitas**
- SSE handler non-blocking; log stream memakai buffer terbatas (drop saat penuh).
- Startup: web siap dalam < 2 dtk; bot menyusul tanpa memblokir UI.
- `RuntimeController` idempoten: start/stop/restart aman dipanggil berulang.
- Kegagalan bot (mis. kredensial salah) tidak mematikan web; status & error tampil di UI.

**Kompatibilitas**
- Python ≥ 3.10 (sesuai `pyproject.toml`), SQLite file di `data/`.
- Bagian inti (audio/telegram/ai) **tidak** berubah perilaku; hanya ditambah seam event.

**Observability**
- Log terstruktur; event bus menerbitkan status/call/log/transcript.
- Audit log tahan lama (tidak ikut dibersihkan oleh retensi transkrip).

## 9. Risiko & mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Refactor `TelegentApp` merusak alur panggilan | Tinggi | Tambah `start()/stop()/restart()` tanpa mengubah `_handle_*`; jaga perilaku; uji dengan fake + smoke test nyata |
| Restart klien in-process (Pyrogram/ntgcalls) tidak stabil / bocor | Tinggi | Serialisasi operasi (lock), tutup penuh sebelum start ulang, uji berulang; fallback: restart container |
| ntgcalls C++ + web server se-proses (thread native) | Sedang | Pertahankan pola dispatch `call_soon_threadsafe`; jangan sentuh state dari thread native |
| Secret bocor via log/error/UI | Tinggi | Redaksi terpusat, masking di schema, tes khusus |
| Kunci enkripsi hilang (volume terhapus) | Sedang | Dokumentasi backup `data/`; kunci hanya untuk secret yang dapat diisi ulang |
| Login web gagal menangani FloodWait/2FA/SessionPasswordNeeded | Sedang | State machine eksplisit + pesan error ter-i18n + tes |
| SQLite konkurensi (write dari bot + web) | Sedang | WAL mode, transaksi singkat, akses via satu engine async |
| Cakupan melebar (monitoring/kontrol) | Sedang | Fase terpisah, milestone demo per fase |

## 10. Dampak pada kode eksisting (refactor)

- `config.py`: tetap sebagai **skema validasi**, tetapi nilai dibaca dari `SettingsStore`
  (DB) dengan fallback env saat bootstrap.
- `app.py` (`TelegentApp`): ditambah kontrol lifecycle (`start`/`stop`/`restart`) dan
  kemampuan menerima setting terbaru untuk panggilan baru; hook event ke `EventBus`.
- `telegram/call_session.py`: tambah callback event (call started/ended, transcript,
  tool call) **tanpa** mengubah pipeline audio; tetap opsional agar test lama tetap lulus.
- `logging_setup.py`: tambah `LoggingHandler` yang meneruskan record ke `EventBus`
  (dengan redaksi secret).
- `__main__.py`: `telegent` menjalankan web+bot; tambah `--no-web` (headless).
- `docker-compose.yml`/`Dockerfile`: single-container multi-stage + volume `data/`.

## 11. Definition of Done (level fitur)

- Semua tiket v1 selesai & digabung; `docs/web-panel` disinkronkan dengan implementasi.
- `uv run pytest -q`, `uv run pyright src/telegent`, `svelte-check`, dan Playwright **hijau** di CI.
- Smoke test manual: dari container bersih → setup admin → isi kredensial → login Telegram →
  ubah setting → terima panggilan → lihat riwayat/transkrip/log → restart dari UI.
- Tidak ada secret yang tampil penuh di UI/log; audit mencatat perubahan.
- README + dokumentasi deployment diperbarui.
