# Spesifikasi — Telegent Web Panel

Dokumen ini adalah kontrak teknis untuk implementasi. Bila ada konflik antara
dokumen ini dan kode, **kode + dokumen harus disinkronkan** dalam PR yang sama.

---

## 1. Aktor & peran

| Aktor | Deskripsi | Hak |
|---|---|---|
| **Admin/Owner** | Satu-satunya pengguna panel (single-tenant). | Semua aksi: konfigurasi, kredensial, login Telegram, monitoring, kontrol proses, audit, akun. |
| **Runtime bot** | `TelegentApp` di proses yang sama. | Membaca setting; menerbitkan event; menyimpan riwayat. |
| **Penelpon (Telegram)** | Pengguna Telegram yang menelepon akun bot. | Tidak mengakses web. Mempengaruhi pemantauan & whitelist. |

Tidak ada RBAC granular di v1 (hanya "admin" tunggal).

---

## 2. Struktur direktori target

```
src/telegent/
  web/
    __init__.py
    app.py                 # create_app(): FastAPI, router, static SPA, lifespan
    deps.py                # dependency: db session, current_admin, runtime, store
    security.py            # hash password, session cookie, CSRF, TOTP
    crypto.py              # SecretCipher (Fernet), load/generate key file
    events.py              # EventBus + tipe event + publish helpers
    log_stream.py          # logging.Handler → EventBus (redaksi)
    runtime.py             # RuntimeController (lifecycle TelegentApp)
    settings_registry.py   # metadata semua setting (label, tipe, grup, hot/restart, secret)
    settings_store.py      # SettingsStore: DB ⇄ pydantic Settings, import .env
    schemas/               # pydantic request/response per domain
    routers/
      auth.py  setup.py  settings.py  credentials.py  telegram.py
      runtime.py  calls.py  tools.py  logs.py  audit.py  health.py
    db/
      base.py              # engine, sessionmaker (SQLite WAL), PRAGMA
      models.py            # ORM models
      migrations/          # Alembic
frontend/                  # SPA SvelteKit (shadcn-svelte)
  src/routes/  src/lib/  static/
```

FastAPI melayani: `/api/*` (JSON/SSE) dan `/` + aset statis (hasil build SPA).

---

## 3. Konfigurasi bootstrap (`.env`)

`.env` **hanya** untuk hal yang dibutuhkan sebelum DB/store tersedia:

| Variabel | Default | Keterangan |
|---|---|---|
| `TELEGENT_DB_URL` | `sqlite+aiosqlite:///./data/telegent.db` | URL DB. |
| `TELEGENT_SECRET_KEY` | *(auto bila kosong)* | Kunci Fernet (base64). Bila kosong → dibuat di `data/.secret_key`. |
| `TELEGENT_DATA_DIR` | `./data` | Direktori DB, `*.session`, `.secret_key`. |
| `TELEGENT_HOST` | `127.0.0.1` | Bind host. |
| `TELEGENT_PORT` | `8080` | Bind port. |
| `TELEGENT_SESSION_TTL_HOURS` | `168` | Umur cookie sesi admin. |
| `TELEGENT_AUTOSTART_BOT` | `true` | Jalankan bot saat boot bila akun sudah login. |

Saat pertama kali, `SettingsStore` melakukan **import `.env` lama** (bila ada) untuk
field yang belum ada di DB, guna migrasi mulus dari deployment CLI.

---

## 4. Registry setting

Setiap setting punya metadata di `settings_registry.py`. Kolom **Penerapan**:
`hot` (berlaku untuk panggilan baru tanpa restart), `restart`
(butuh restart klien runtime), atau `bootstrap` (di luar UI).

| Key | Grup | Tipe | Default | Validasi | Penerapan | Secret |
|---|---|---|---|---|---|---|
| `telegram_api_id` | kredensial | int | — | > 0, wajib | restart | tidak |
| `telegram_api_hash` | kredensial | str | — | 32 hex, wajib | restart | **ya** |
| `gemini_api_key` | kredensial | str | — | non-kosong, min. 20 karakter | restart | **ya** |
| `telegram_session_name` | akun_telegram | str | `userbot_session` | pola nama berkas | restart | tidak |
| `gemini_model` | model_ai | str | `gemini-3.1-flash-live-preview` | pilihan/model valid | hot | tidak |
| `system_instruction` | persona | text | *(default kode)* | non-kosong | hot | tidak |
| `greeting_prompt` | persona | text | *(default kode)* | non-kosong | hot | tidak |
| `idle_prompt_instruction` | persona | text | *(default kode)* | non-kosong | hot | tidak |
| `idle_farewell_instruction` | persona | text | *(default kode)* | non-kosong | hot | tidak |
| `allowed_user_ids` | kebijakan_akses | list[int] | `[]` (= semua) | tiap item int | hot | tidak |
| `max_concurrent_calls` | kebijakan_akses | int | `4` | ≥ 1 | hot | tidak |
| `max_call_duration` | kebijakan_akses | float | `600` | ≥ 0 (0=∞) | hot | tidak |
| `max_calls_per_window` | kebijakan_akses | int | `5` | ≥ 0 (0=∞) | hot | tidak |
| `call_window_seconds` | kebijakan_akses | float | `60` | > 0 | hot | tidak |
| `idle_enabled` | anti_idle | bool | `true` | — | hot | tidak |
| `idle_prompt_seconds` | anti_idle | float | `15` | > 0 | hot | tidak |
| `idle_hangup_seconds` | anti_idle | float | `15` | > 0 | hot | tidak |
| `log_level` | logging | enum | `INFO` | DEBUG/INFO/WARNING/ERROR | hot | tidak |
| `bot_autostart` | aplikasi | bool | `true` | — | hot | tidak |
| `calls_retention_days` | aplikasi | int | `30` | ≥ 0 (0=simpan selamanya) | hot | tidak |
| `transcripts_retention_days` | aplikasi | int | `30` | ≥ 0 | hot | tidak |
| `store_transcripts` | aplikasi | bool | `true` | — | hot | tidak |
| `log_buffer_lines` | aplikasi | int | `1000` | 100–10000 | hot | tidak |
| `tg_sample_rate` | audio | int | `48000` | lanjutan (read-only di UI) | restart | tidak |
| `tg_frame_ms` | audio | int | `10` | lanjutan | restart | tidak |
| `gemini_input_rate` | audio | int | `16000` | lanjutan | restart | tidak |
| `gemini_output_rate` | audio | int | `24000` | lanjutan | restart | tidak |

**Aturan `hot`:** `TelegentApp.settings` diganti dengan objek `Settings` baru hasil
`SettingsStore.build()`. Panggilan **baru** memakai nilai baru. Panggilan yang **sedang
berjalan** tetap memakai snapshot lama (didokumentasikan di UI sebagai catatan).

**Aturan `restart`:** perubahan ditandai "pending restart"; UI menampilkan badge.
Aksi **Terapkan & Restart** memanggil `RuntimeController.restart()`.

**Perubahan kredensial juga menandai koneksi Gemini/Telegram perlu dibangun ulang.**

> **Lokasi berkas sesi (penting):** `session_dir` bukan setting UI, tetapi selalu
> dipaksa menunjuk `TELEGENT_DATA_DIR` saat `SettingsStore.build_settings()` menyusun
> `Settings`. Tanpa itu, runtime akan mencari `*.session` di direktori kerja dan tidak
> menemukan sesi yang dibuat melalui login web.

---

## 5. Model data

Dialek: SQLite. Gunakan `PRAGMA journal_mode=WAL`, `foreign_keys=ON`.
Semua tabel punya `created_at`/`updated_at` (UTC) kecuali dinyatakan lain.

### 5.1 `admin_user` (satu baris)
| Kolom | Tipe | Catatan |
|---|---|---|
| id | int PK | |
| username | str unique | |
| password_hash | str | argon2/bcrypt |
| totp_secret_enc | str? | terenkripsi; null bila 2FA mati |
| totp_enabled | bool | default false |
| failed_attempts | int | untuk lockout |
| locked_until | datetime? | |
| last_login_at | datetime? | |
| locale | str | `id`/`en` |
| theme | str | `light`/`dark`/`system` |

### 5.2 `app_setting`
| Kolom | Tipe | Catatan |
|---|---|---|
| key | str PK | sesuai registry |
| value | text | JSON-encoded; untuk secret → ciphertext |
| encrypted | bool | true untuk field secret |
| updated_at | datetime | |
| updated_by | str | username admin |

### 5.3 `telegram_account` (satu baris)
| Kolom | Tipe | Catatan |
|---|---|---|
| id | int PK | selalu `1` (keputusan: satu akun aktif) |
| phone | str? | nomor terdaftar |
| tg_user_id | int? | id akun setelah login |
| tg_username | str? | @username |
| tg_first_name | str? | |
| session_name | str? | nama sesi dipakai saat login; dibandingkan dengan `telegram_session_name` untuk mendeteksi `session_mismatch` |
| status | str | `not_configured`/`logged_out`/`logged_in`/`error` |
| last_error | str? | **kode galat stabil** terakhir (bukan pesan bebas), mis. `code_invalid` |
| logged_in_at | datetime? | |

### 5.4 `login_flow` (state sementara login)
| Kolom | Tipe | Catatan |
|---|---|---|
| id | int PK | `AUTOINCREMENT` — id tidak pernah dipakai ulang sehingga `flow_id` dari API selalu unik |
| phone | str | |
| phone_code_hash | str | dari `send_code` (**tidak pernah** masuk log/audit) |
| status | str | `code_sent`/`awaiting_password`/`done` |
| created_at | datetime | TTL ±10 menit; dibersihkan berkala (tiap 5 menit) |
| expires_at | datetime | |

### 5.5 `call_record`
| Kolom | Tipe | Catatan |
|---|---|---|
| id | int PK | |
| tg_call_id | int | id panggilan Telegram |
| user_id | int | id penelpon |
| user_display | str? | nama/@username bila diketahui |
| outcome | str | `pending`/`answered`/`rejected_whitelist`/`rejected_ratelimit`/`rejected_capacity`/`rejected_duplicate`/`error` |
| end_reason | str? | `caller_hangup`/`ai_end_call`/`max_duration`/`idle`/`panel_hangup`/`rejected`/`error` |
| started_at | datetime | saat panggilan masuk (Q12); di-*update* ke waktu ACTIVE bila panggilan dijawab |
| ended_at | datetime? | |
| duration_sec | int? | durasi sesi aktif (0 untuk panggilan ditolak) |
| tool_call_count | int | default 0 |
| transcript_count | int | default 0 |

> **Catatan Fase 3 (Q12):** baris dibuat saat panggilan **masuk**, sehingga
> penolakan (whitelist/rate-limit/kapasitas/duplikat) tetap tercatat dengan
> `outcome` + `end_reason='rejected'`. Untuk panggilan yang dijawab,
> `started_at` digeser ke waktu CALL ACTIVE agar konsisten dengan `duration_sec`
> yang diukur runtime sejak sesi media siap.

### 5.6 `transcript_entry`
| Kolom | Tipe | Catatan |
|---|---|---|
| id | int PK | |
| call_record_id | int FK | on delete cascade |
| speaker | str | `caller`/`ai` |
| text | text | |
| at | datetime | |

### 5.7 `tool_call_record`
| Kolom | Tipe | Catatan |
|---|---|---|
| id | int PK | |
| call_record_id | int FK | cascade |
| name | str | |
| args_json | text | |
| result_json | text | |
| status | str | `ok`/`error`/`timeout`/`cancelled` |
| duration_ms | int | |
| at | datetime | |

### 5.8 `tool_config`
| Kolom | Tipe | Catatan |
|---|---|---|
| name | str PK | mis. `get_current_datetime` |
| enabled | bool | default true |
| config_json | text | parameter (mis. `{"default_timezone":"Asia/Jakarta"}`) |

### 5.9 `audit_log`
| Kolom | Tipe | Catatan |
|---|---|---|
| id | int PK | |
| actor | str | username admin |
| action | str | `setting.update`/`credential.update`/`runtime.restart`/`telegram.login`/… |
| target | str? | key/objek |
| before_json | text? | nilai sebelum (secret **dimask**) |
| after_json | text? | nilai sesudah (secret **dimask**) |
| ip | str? | |
| at | datetime | |

`audit_log` **tidak** dibersihkan oleh retensi transkrip.

---

## 6. API REST

Semua di bawah `/api`. Auth via session cookie (kecuali ditandai publik).
Mutasi wajib menyertakan header `X-CSRF-Token` yang cocok dengan cookie CSRF.
Error konsisten: `{"error": {"code": "...", "message": "...", "fields": {...}}}`.

### 6.1 Setup & auth
| Method | Path | Body | Respons | Catatan |
|---|---|---|---|---|
| GET | `/setup/status` | — | `{needs_setup: bool}` | publik |
| POST | `/setup/admin` | `{username, password}` | `{ok}` | publik, hanya bila belum ada admin |
| POST | `/auth/login` | `{username, password, totp?}` | `{ok}` + set cookie | rate-limited |
| POST | `/auth/logout` | — | `{ok}` | |
| GET | `/auth/me` | — | `{username, totp_enabled, locale, theme}` | |
| PATCH | `/auth/me` | `{locale?, theme?}` | `{ok}` | |
| POST | `/auth/password` | `{current, new}` | `{ok}` | |
| POST | `/auth/totp/setup` | — | `{secret, otpauth_uri, qr_svg}` | |
| POST | `/auth/totp/enable` | `{code}` | `{ok}` | |
| POST | `/auth/totp/disable` | `{code}` | `{ok}` | |

### 6.2 Settings
| Method | Path | Body | Respons |
|---|---|---|---|
| GET | `/settings` | — | daftar setting bergrup (secret dimask) + `pending_restart: bool` |
| GET | `/settings/schema` | — | metadata registry (label i18n, tipe, grup, validasi, penerapan) |
| PUT | `/settings` | `{changes: {key: value, ...}}` | `{applied: [...], needs_restart: [...]}` |

### 6.3 Kredensial
| Method | Path | Body | Respons |
|---|---|---|---|
| PUT | `/credentials/telegram` | `{api_id, api_hash}` | `{ok}` (disimpan terenkripsi, status → restart) |
| PUT | `/credentials/gemini` | `{api_key}` | `{ok}` |
| POST | `/credentials/validate` | `{kind: telegram|gemini}` | `{valid, message}` |

Validasi Telegram: `get_me`/koneksi ringan dengan sesi yang ada atau cek format.
Validasi Gemini: panggilan model ringan / cek format + opsi ping bila memungkinkan.

### 6.4 Telegram (akun & login)
| Method | Path | Body | Respons |
|---|---|---|---|
| GET | `/telegram/status` | — | `{status, phone?, user?, last_error?, logged_in_at?, credentials_configured, session_name, session_mismatch}` |
| POST | `/telegram/login/start` | `{phone}` | `{flow_id, next: "code"}` |
| POST | `/telegram/login/verify` | `{flow_id, code}` | `{next: "password"\|"done"}` |
| POST | `/telegram/login/password` | `{flow_id, password}` | `{ok}` |
| POST | `/telegram/login/cancel` | `{flow_id}` | `{ok}` |
| POST | `/telegram/logout` | — | `{ok}` |

Semua mutasi memerlukan sesi admin + `X-CSRF-Token`; `GET /status` cukup sesi admin.
`login/start` membatalkan flow yang masih terbuka (single-tenant, satu alur aktif).

> **`GET /telegram/status` bersifat baca.** Status yang tidak lagi cocok dengan
> berkas sesi di disk diturunkan di respons (`status` menjadi `logged_out`) tanpa
> menulis ke database; koreksi disimpan saat admin logout atau login berikutnya.

Penanganan error: `phone_invalid`, `code_invalid`, `code_expired`, `password_invalid`,
`flood_wait`, `api_credentials_missing`, `telegram_unreachable`, `session_invalid`,
`telegram_error`, `flow_not_found`, `flow_expired`, `bot_running`, `already_logged_in`,
`account_not_logged_in`.

> **`telegram_unreachable`** dipakai khusus untuk kegagalan jaringan ke Telegram,
> agar tidak bentrok dengan `network_error` yang berarti kegagalan jaringan ke API panel.

> **`flood_wait`:** nilai tunggu dikirim pada `error.fields.retry_after` (dalam detik),
> mengikuti amplop galat §6. Contoh: `{"error": {"code": "flood_wait", "fields":
> {"retry_after": 300}}}`.
>
> **`bot_running` (409):** login maupun logout ditolak selama runtime `running` —
> berkas sesi dipakai bot yang sedang hidup.
>
> **`session_mismatch`:** bila `telegram_session_name` diubah setelah login, baris akun
> tetap `logged_in` (sesi lama masih ada) tetapi UI menampilkan perlunya login ulang (Q10).

### 6.5 Runtime
| Method | Path | Body | Respons |
|---|---|---|---|
| GET | `/runtime/status` | — | `{running, state, since?, model, active_calls, logged_in_user?, last_error?}` |
| POST | `/runtime/start` | — | `{ok}` |
| POST | `/runtime/stop` | — | `{ok}` |
| POST | `/runtime/restart` | — | `{ok}` |
| POST | `/runtime/apply` | — | status runtime setelah perubahan tertunda diterapkan |

> **Catatan Fase 1:** `GET /runtime/status` dan `POST /runtime/apply` diimplementasikan
> lebih awal (tiket B3/C2) karena UI sudah membutuhkan keduanya. Kontrol
> start/stop/restart eksplisit tetap menjadi tiket F1.

### 6.6 Panggilan
| Method | Path | Query | Respons |
|---|---|---|---|
| GET | `/calls/active` | — | daftar sesi aktif (user, durasi, state, transcript tail) |
| GET | `/calls` | `page, page_size, from?, to?, user?, outcome?` | daftar riwayat + total |
| GET | `/calls/{id}` | — | detail + counts |
| GET | `/calls/{id}/transcript` | — | daftar transkrip |
| GET | `/calls/{id}/tools` | — | daftar tool call |
| POST | `/calls/{id}/hangup` | — | `{ok}` (akhiri panggilan aktif) |

### 6.7 Tool
| Method | Path | Body | Respons |
|---|---|---|---|
| GET | `/tools` | — | daftar tool (name, enabled, config, schema) |
| PUT | `/tools/{name}` | `{enabled?, config?}` | `{ok}` |

### 6.8 Log & event (SSE)
| Method | Path | Respons |
|---|---|---|
| GET | `/events/stream` | `text/event-stream` — status + panggilan + transkrip |
| GET | `/logs/stream` | `text/event-stream` — log (ring buffer awal + live) |
| GET | `/audit` | daftar audit (paginasi) |
| GET | `/healthz` | `{ok, version, db, runtime}` (publik, tanpa detail sensitif) |

---

## 7. Skema event SSE

Format: `event: <tipe>\ndata: <json>\n\n`. Sertakan `id:` untuk resume ringan dan
`retry: 3000`. Heartbeat tiap 15 dtk.

| `event` | Payload (contoh) |
|---|---|
| `status` | `{"running": true, "state": "active", "active_calls": 2}` |
| `call.incoming` | `{"user_id": 123, "call_id": 9, "outcome": "pending"}` |
| `call.started` | `{"call_id": 9, "user_id": 123, "started_at": "..."}` |
| `call.ended` | `{"call_id": 9, "duration_sec": 42, "end_reason": "caller_hangup"}` |
| `transcript` | `{"call_id": 9, "speaker": "caller", "text": "...", "at": "..."}` |
| `tool_call` | `{"call_id": 9, "name": "end_call", "status": "ok", "duration_ms": 12}` |
| `log` | `{"level": "INFO", "logger": "telegent.call", "message": "...", "at": "..."}` |
| `runtime.error` | `{"message": "..."}` |

Log stream memakai buffer terbatas (`log_buffer_lines`); saat klien terlalu lambat,
event di-drop (bukan memblok bangunan penerbit).

---

## 8. Alur kunci

### 8.1 First-run setup
1. Buka `/` → `GET /setup/status` → `needs_setup: true` → SPA arahkan ke `/setup`.
2. `POST /setup/admin` (username+password) → buat admin → auto-login.
3. Wizard lanjut: isi kredensial Telegram & Gemini → validasi → simpan.
4. Wizard: login Telegram → `send_code` → `verify` → (bila perlu) `password`.
5. Wizard: panggil `POST /runtime/start` → status `active`.

### 8.2 Login admin
`POST /auth/login` → verifikasi hash (+ TOTP bila aktif) → set cookie sesi + CSRF.
Gagal → catat `failed_attempts`; melebihi ambang → lockout sementara.

### 8.3 Ubah setting
1. UI ambil `/settings` + `/settings/schema`.
2. `PUT /settings {changes}` → store validasi tiap key → simpan → tulis audit
   (dengan masking) → bila `hot`: perbarui `app.settings`; bila `restart`: tandai pending.
3. Respons menyebut `applied` dan `needs_restart` → UI tampilkan badge & tombol
   **Terapkan & Restart** bila perlu.

### 8.4 Login Telegram
`login/start` membuat klien Pyrogram tak-terautentikasi (butuh api_id/hash sudah ada),
`send_code(phone)` → simpan `phone_code_hash` ke `login_flow` (TTL ±10 menit) →
`verify(code)`:
- sukses → sesi disimpan sebagai `*.session` di `TELEGENT_DATA_DIR`, status `logged_in`
  (beserta `tg_user_id`/username/nama) → audit.
- `SessionPasswordNeeded` → alur berpindah ke `awaiting_password` → `check_password`.
- error → `last_error` diisi **kode galat stabil**, bukan pesan mentah; `phone_code_hash`,
  kode OTP, dan password tidak pernah ditulis ke log (nilai Sensitive didaftarkan ke
  `SecretRedactor` sebagai pengaman kedua).
- `login/cancel` membuang flow; flow kedaluwarsa dibersihkan tiap 5 menit.
- `logout` memanggil `log_out` pada klien lalu menghapus seluruh `*.session*` di direktori
  data (keputusan satu akun aktif). Kegagalan sisi Telegram tidak menghalangi penghapusan
  lokal; kode galatnya dicatat di `last_error`.

> Login/logout ditolak dengan `bot_running` selama runtime berjalan; setelah login sukses
> admin diminta menjalankan bot dari panel (kontrol penuh menyusul di F1/F2).

### 8.5 Monitoring
- Runtime menerbitkan event ke `EventBus`; endpoint SSE meneruskan ke klien.
- `call_record` dibuat saat panggilan **masuk** (Q12, termasuk yang ditolak) dan
  ditutup saat panggilan selesai; transkrip & tool call ditulis saat event
  terkait terjadi (opsional bila `store_transcripts=false`, Q13).
- Penulisan database dilakukan oleh satu task penulis (`CallRecorder`) di luar
  jalur audio: hook hanya mengantrekan pekerjaan, dan antrean penuh berarti
  data dibuang — bukan menunggu.
- `store_transcripts=false` mematikan penyimpanan **dan** penyiaran teks
  transkrip; `tool_call_record` tetap disimpan (metadata, bukan rekaman suara).
- Secret disamarkan pada transkrip serta argumen/hasil tool sebelum ditulis maupun
  disiarkan.

### 8.6 Kontrol runtime
- `start`: bangun & jalankan `TelegentApp` sebagai task. `stop`: sinyal stop + tunggu
  `_shutdown`. `restart`: `stop` lalu `start` (di bawah lock, idempoten).
- Bila belum login/berkredensial → `start` mengembalikan status `needs_login`/`not_configured`
  (bukan error keras), UI mengarahkan ke wizard.

---

## 9. Keamanan

- **Password:** hash argon2 (fallback bcrypt); verifikasi konstan-waktu.
- **Sesi:** cookie `httpOnly`, `SameSite=Lax`, TTL `TELEGENT_SESSION_TTL_HOURS`;
  token sesi acak (≥128 bit), disimpan server-side (tabel/`itsdangerous`).
- **CSRF:** token per-sesi; wajib pada semua mutasi.
- **Rate-limit login** per IP+username; lockout eksponensial.
- **Secret:** hanya Fernet ciphertext di DB; UI selalu masking (`••••`); log handler
  meredaksi nilai secret; audit menyimpan masking.
- **Header:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`; CSP ketat untuk SPA.
- **Tidak ada TLS bawaan** (akses privat). Dokumentasikan penggunaan VPN/tunnel;
  cookie tidak memakai flag `Secure` agar tetap berfungsi di HTTP lokal.

---

## 10. i18n

- Frontend: katalog `id` (default) & `en`; pilihan bahasa disimpan di `admin_user.locale`.
- Backend: pesan error memakai **kode stabil** (`code`) + opsi `message` default;
  UI menerjemahkan berdasarkan `code`.
- Format tanggal/angka mengikuti locale; zona waktu default `Asia/Jakarta`.

---

## 11. Penanganan error & batas

| Kondisi | Perilaku |
|---|---|
| Kredensial belum diisi | Runtime `not_configured`; wizard mengarahkan; bukan 500. |
| Gemini API key invalid | Status runtime `error` + `last_error`; web tetap hidup. |
| Akun Telegram logout | Status `logged_out`; runtime berhenti menerima; UI tawarkan login. |
| FloodWait Telegram | Kembalikan `flood_wait` + `retry_after`; UI tampilkan hitung mundur. |
| DB terkunci (SQLite) | Retry transaksi singkat; WAL; error jujur bila gagal. |
| SSE klien putus | Auto-reconnect (EventSource); kirim ring buffer log terbaru saat sambung. |
| Perubahan `restart` tertunda | Badge jelas; apply hanya saat admin menekan tombol. |

---

## 12. Non-fungsional (ringkas)

- Skema DB via Alembic; upgrade otomatis saat boot (`alembic upgrade head`).
- Semua handler async; operasi berat (bcrypt, validasi kredensial) dijalankan tanpa
  memblok loop (threadpool bila perlu).
- Redaksi secret teruji (unit test khusus).
- Log & event tidak memuat nilai secret/PII berlebih.
