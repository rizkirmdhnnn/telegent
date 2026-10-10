# Prompt — Implementasi Fase 2: Login Telegram via Web (D1–D3)

Gunakan prompt ini apa adanya untuk sesi/mode agent baru.

---

Kerjakan **Fase 2 (tiket D1, D2, D3)** di repo `telegent`: layanan
antarmuka web untuk **login akun Telegram tanpa terminal**. Adminconnects
akun Telegram-nya dari panel (nomor → kode → password 2FA), lalu bot siap
menerima panggilan.

## Konteks repo (WAJIB dibaca dulu)

- Repo: `/Users/rizkirmdhn/Documents/reseach/telegent`
- Branch: `feat/web-panel-phase-1` — **buat branch baru** `feat/web-panel-phase-2`
- Pyrogram 2.0.106 (MTProto userbot) + ntgcalls + Gemini Live API
- Monolit 1 proses: FastAPI menyajikan SPA dan menjalankan `TelegentApp`
  di event loop yang sama. **Jangan pisahkan proses.**

### Sudah selesai (jangan diulang)
Fase 0 (A1–A8) dan Fase 1 (B1–B3, C1–C4). Endpoint yang sudah ada:

```
GET    /api/healthz              GET    /api/setup/status   POST /api/setup/admin
POST   /api/auth/login|logout|totp/setup|totp/enable|totp/disable|password
GET    /api/auth/me              PATCH  /api/auth/me
GET    /api/settings             GET    /api/settings/schema   PUT  /api/settings
PUT    /api/credentials/telegram|gemini    POST /api/credentials/validate
GET    /api/tools                PUT    /api/tools/{name}
GET    /api/runtime/status       POST   /api/runtime/apply
GET    /api/audit                GET    /api/audit/actions
```

### Dokumen acuan (baca sebelum menulis kode)
- `docs/web-panel/tickets/D1-telegram-login-service.md`
- `docs/web-panel/tickets/D2-telegram-api.md`
- `docs/web-panel/tickets/D3-telegram-ui.md`
- `docs/web-panel/spec.md` — terutama **§5.3 `telegram_account`**,
  **§5.4 `login_flow`**, **§6.4 endpoint**, **§8.4 alur**, **§9 keamanan**
- `docs/web-panel/plan.md` §7 (fase) dan §10 (risiko)
- `docs/web-panel/open-questions.md` — **Q10** (lokasi/penamaan sesi) dan
  **Q11** (2FA wajib didukung) sudah diputuskan; ikut reCaptcha soal lain.

## Keputusan produk yang SUDAH dikunci (jangan dibuka ulang)

- Single-tenant, **satu akun Telegram aktif** per deployment.
- Ganti akun = logout + login baru. Tidak ada multi-akun.
- Tabrakan harga: `ALLOWED_USER_IDS` kosong berarti semua orang boleh menelepon.
- Akses privat (VPN/tunnel), tanpa TLS bawaan.
- Panel dwibahasa (id/en), default Indonesia. Tanpa teks Indonesia mentah di UI.

## Ruang lingkup

**D1 — `src/telegent/web/telegram_login.py`**
`TelegramLoginService` yang mengelola klien Pyrogram tak-terautentikasi:

| Metode | Perilaku |
|---|---|
| `start(phone)` | `send_code` → simpan `phone_code_hash` → `login_flow` status `code_sent` |
| `verify(flow_id, code)` | `sign_in`; bila `SessionPasswordNeeded` → status `awaiting_password` |
| `submit_password(flow_id, password)` | `check_password` → sukses: `telegram_account.status=logged_in`, simpan `tg_user_id/username/first_name`, `logged_in_at` |
| `logout()` | `log_out` pada klien + hapus berkas `*.session` → status `logged_out` |
| `cancel(flow_id)` | Buang state flow yang belum selesai |

- Semua exception Pyrogram dipetakan ke **kode stabil**, bukan pesan mentah:
  `phone_invalid`, `code_invalid`, `code_expired`, `password_invalid`,
  `flood_wait` (+`retry_after` dari `FloodWait.value`), `session_password_needed`,
  `api_credentials_missing`, `network_error`.
- **Nilai `phone_code_hash`, kode OTP, dan password TIDAK BOLEH masuk log.**
  Gunakan redactor yang sudah ada (`telegent.web.log_stream.SecretRedactor`).
- Bersihkan `login_flow` kedaluwarsa (TTL ±10 menit) secara berkala.
- Klien harus dibuat dengan `workdir` = `TELEGENT_DATA_DIR` dan
  `session_name` = setting `telegram_session_name` (dari `SettingsStore`).

**D2 — `src/telegent/web/routers/telegram.py`**

```
GET  /api/telegram/status     → {status, phone?, user?, last_error?}
POST /api/telegram/login/start    {phone}                → {flow_id, next}
POST /api/telegram/login/verify   {flow_id, code}        → {next}
POST /api/telegram/login/password {flow_id, password}    → {ok}
POST /api/telegram/login/cancel   {flow_id}              → {ok}
POST /api/telegram/logout         → {ok}
```

- Semua endpoint wajib admin + CSRF (`CsrfDep`), kecuali `GET /status`
  yang cukup `AdminDep`.
- Tanpa kredensial Telegram → `api_credentials_missing`, **bukan** HTTP 500.
- Setiap login/logout/cancel → `record_audit` (`telegram.login`,
  `telegram.logout`). Secret tidak boleh masuk `before/after`.

**D3 — `frontend/src/routes/(app)/telegram/+page.svelte`**

- Halaman `/telegram` (hapus penanda "Segera" dari nav item `nav.telegram`).
- Wizard bertahap: (1) nomor telepon, (2) kode OTP, (3) password 2FA (kondisional),
  (4) status sukses.
- Tampilkan status akun saat ini (nama, @username, id, waktu login).
- Tombol logout + tombol "Mulai ulang alur".
- **Hitung mundur FloodWait** dari `retry_after`.
- Setelah login sukses: tawarkan "Jalankan bot" (menuju `/runtime/status`) dan
  arahkan ke kredensial bila belum terisi.

## Aturan Rekayasa (WAJIB dipatuhi — sudah dilanggar sekali di Fase 1)

1. **Semua teks UI lewat `t()`.** Tidak ada string Indonesia/Inggris mentah di
   `.svelte`. Kunci baru wajib ada di `id.json` **dan** `en.json` (verifikasi
   jumlah kunci kedua file identik — pernah tidak sinkron).
2. **Pesan galat dari `code`, bukan `message`.** Pakai `apiErrorMessage()`
   dari `$lib/api`; backend tetap mengirim `message` sebagai cadangan.
3. **Field secret TIDAK PERNAH diisi dari nilai yang sudah ter-mask.**
   Pakai flag `is_set`, `type="password"`, dan "kosong = pertahankan yang
   tersimpan" (pola ini sudah dipakai `/credentials`).
4. **Backend memvalidasi input.** Tambah field baru → perbarui
   `docs/web-panel/spec.md` bila kontrak berubah.
5. **Exception yang diketahui wajib `# noqa: BLE001` + alasan.**-repo memakai
   ini konsisten; `except: pass` tanpa alasan dilarang.
6. **Alembic tidak boleh jalan di dalam event loop.** Gunakan
   `upgrade_to_head_async()` (sudah ada) bila perlu migrasi baru.
7. **Jangan robusto-kan `Database.session()` dengan try/except di dalamnya** —
   context manager itu me-rollback saat handler melempar galat, sehingga
   pencatatan ke tabel ikut hilang. Tulis state di transaksi terpisah bila perlu.
8. **Tailwind v4**: `dark:` memakai kelas `.dark` via `@custom-variant` di
   `frontend/src/app.css`. Jangan pakai warna hardcoded.
9. **Pengujian tidak boleh menyentuh jaringan.** Semua tes memakai fake untuk
   Pyrogram/ntgcalls/Gemini — stub `Client` lewat `monkeypatch.setattr`.
10. **Tes frontend yang butuh `frontend/build` harus di-`skip` bila build
    belum ada** (`pytest.mark.skipif`) — kalau tidak, CI merah.

## Definition of Done

- [ ] `uv run pytest -q` hijau (semua tes lama tetap hijau; **tidak boleh**
      mengorbankan cakupan tes yang sudah ada).
- [ ] `uv run pyright src/telegent` → 0 error.
- [ ] `cd frontend && npm run check` → 0 error; `npm run build` sukses.
- [ ] Tidak ada secret/kode OTP/password di log (ada tes yang membuktikan).
- [ ] Semua kunci i18n baru ada di `id.json` **dan** `en.json`.
- [ ] Login berhasil **terbukti** oleh tes dengan Pyrogram di-stub
      (termasuk jalur `SessionPasswordNeeded` → password).
- [ ] FloodWait mengembalikan `retry_after`, bukan crash.
- [ ] `docs/web-panel/todos.md` Fase 2 ditandai selesai; `spec.md` disinkronkan.
- [ ] Satu commit per tiket dengan pesan gaya repo:
      `feat(web): D1 …`, `feat(web): D2 …`, `feat(web): D3 …` (bahasa Indonesia).

## Di luar cakupan

Jangan kerjakan: riwayat panggilan/pemantauan (Fase 3/E), start/stop/restart
eksplisit (Fase 4/F1), tool kustom, multi-akun Telegram, atau tiket G/H.

## Cara kerja yang diminta

1. Baca dokumen acuan dan kode yang relevan **sebelum** menulis.
2. Kerjakan D1 → tes → D2 → tes → D3 → tes (satu per satu, jangan semua
   sekaligus).
3. Jalankan `pytest`, `pyright`, dan `svelte-check` setelah setiap langkah.
4. Jika menemukan keputusan yang belum ditetapkan (mis. perilaku `session_name`
   diubah, atau login saat bot sedang berjalan), **tanyakan dulu** — jangan
   menebak.
5. Laporkan di akhir: apa yang berubah, hasil verifikasi, dan temuan/gagal
   yang tersisa.