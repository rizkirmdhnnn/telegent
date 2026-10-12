# Deployment Telegent (Docker + panel web)

Panduan self-host untuk Telegent: satu container menjalankan **panel web** dan
**bot** sekaligus. Keduanya berada dalam satu proses (FastAPI + bot pada event
loop yang sama), jadi tidak ada container kedua dan tidak ada reverse proxy wajib.

Rujukan: [`plan.md`](plan.md) §7, [`spec.md`](spec.md) §3 & §9.

---

## 1. Jalankan

```bash
mkdir -p data
docker compose up -d
docker compose logs -f
```

Buka panel di **http://127.0.0.1:8080**.

Tidak ada file `.env` yang wajib ada. Langkah pertama di panel adalah membuat
akun admin; setelah itu kredensial Telegram & Gemini diisi dari UI. Container
tetap boot dengan benar meski tidak satu pun kredensial terisi — mode web
sengaja tidak memaksa `Settings()` valid saat start.

| Env | Default | Keterangan |
|---|---|---|
| `TELEGENT_DATA_DIR` | `/data` (container) | Direktori DB, `*.session`, `.secret_key`. |
| `TELEGENT_HOST` | `0.0.0.0` di compose | Bind host **di dalam container**. |
| `TELEGENT_PORT` | `8080` | Port panel. |
| `TELEGENT_AUTOSTART_BOT` | `true` | Jalankan bot saat boot bila kredensial + sesi sudah siap. |
| `TELEGENT_SESSION_TTL_HOURS` | `168` | Umur cookie sesi admin. |
| `TELEGENT_SECRET_KEY` | *(kosong)* | Kunci Fernet. Bila kosong → dibuat di `data/.secret_key`. |
| `TELEGENT_DB_URL` | `sqlite+aiosqlite:////data/telegent.db` | Override bila ingin DB di luar `data/`. |

> **Satu nama untuk direktori data.** `TELEGENT_DATA_DIR` adalah satu-satunya
> nama yang dipakai image. Nilai lama `TELEGRAM_SESSION_DIR` masih dibaca
> `Settings` sebagai alias kompatibilitas, tapi **jangan** menetapkannya di
> compose/`Dockerfile` — jika kedua env diisi dengan nilai berbeda, database dan
> berkas `*.session` akan terpisah.

### Alur pertama kali

1. Buka `http://127.0.0.1:8080` → diarahkan ke `/setup`.
2. Buat akun admin (langsung login).
3. **Kredensial**: isi `telegram_api_id`, `telegram_api_hash`, `gemini_api_key`.
4. **Telegram**: masukkan nomor → kode OTP → (bila perlu) password 2FA.
   Setelah itu berkas `data/userbot_session.session` muncul.
5. **Runtime**: tekan mulai. Status berubah ke `running`.

---

## 2. Akses privat (VPN/tunnel)

Panel **tidak** membawa TLS dan tidak dimaksudkan untuk diekspos langsung. Yang
tersedia bawaan hanya session cookie `httpOnly` + `SameSite=Lax` (tanpa flag
`Secure` agar tetap berfungsi di HTTP lokal), jadi tetap perlu lapisan jaringan
yang tepercaya.

| Cara | Catatan |
|---|---|
| **SSH tunnel** (paling umum) | `ssh -N -L 8080:127.0.0.1:8080 user@server`, lalu buka `http://127.0.0.1:8080`. Tidak butuh domain maupun TLS. |
| **Tailscale / WireGuard** | Server jadi anggota mesh privat; panel tetap bind loopback di host, diakses lewat IP mesh. |
| **Reverse proxy + TLS** | Bila memakai domain: taruh Caddy/nginx di depan, publish `127.0.0.1:8080`, lalu proksi HTTPS ke sana. |

Yang **tidak** boleh: `ports: - "8080:8080"` (tanpa `127.0.0.1:`) pada host publik.

---

## 3. Yang harus di-backup

Satu direktori: `./data` di host (`/data` di dalam container).

| Berkas | Isi | Hilang → akibat |
|---|---|---|
| `telegent.db` | Akun admin, setting, kredensial terenkripsi, akun Telegram, riwayat panggilan, transkrip, audit log. | Kehilangan seluruh panel dan riwayat. |
| `.secret_key` | Kunci enkripsi Fernet. | **Secret yang tersimpan tidak dapat dibaca lagi.** |
| `*.session` | Sesi Telegram (auth key). | Bot harus login ulang dari panel. |

> **Kehilangan `.secret_key` bersifat permanen.** Nilai `telegram_api_hash` dan
> `gemini_api_key` terenkripsi dengan kunci itu. Admin tetap bisa mengisinya
> ulang lewat panel, tetapi nilai lama tidak dapat dipulihkan. Karena itu `data/`
> tidak boleh ikut terhapus bersama drive dan tidak boleh di-*reset* saat mereset
> password admin.

Backup konsisten saat bot sedang berjalan (SQLite memakai mode WAL):

```bash
# Snapshot database lewat API backup SQLite (aman tanpa menghentikan proses)
docker compose exec telegent python -c "\
import sqlite3; src=sqlite3.connect('/data/telegent.db'); \
dst=sqlite3.connect('/tmp/backup.db'); src.backup(dst); dst.close(); src.close()"
mkdir -p backup
docker compose cp telegent:/tmp/backup.db ./backup/telegent.db
docker compose cp telegent:/data/.secret_key ./backup/.secret_key
docker compose cp telegent:/data/userbot_session.session ./backup/ || true
```

Sederhananya, untuk deployment non-kritis: hentikan container, salin seluruh
`./data`, jalankan lagi.

```bash
docker compose down
cp -a data "data-backup-$(date +%F)"
docker compose up -d
```

---

## 4. Migrasi dari deployment `.env` lama

Sebelum fase web panel, Telegent dikonfigurasi lewat `.env`
(`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `GEMINI_API_KEY`, `ALLOWED_USER_IDS`, …).
Panel memindahkan sumber kebenaran ke database, tetapi **mengimpor** nilai `.env`
sekali saja, saat database masih kosong.

1. Letakkan `.env` lama di root proyek (pola variabelnya ada di
   [`.env.example`](../../.env.example)).
2. `docker compose up -d`, lalu cek log:

   ```bash
   docker compose logs | grep "Mengimpor"
   # "Mengimpor N setting dari konfigurasi .env lama."
   ```

3. Buka panel, buat akun admin, periksa halaman **Pengaturan** — nilainya sudah
   ada.
4. Login Telegram dari panel (atau `docker compose run --rm -it telegent
   --no-web` untuk login interaktif sekali).
5. Setelah semua setting tampil benar di panel, `.env` boleh dibuang dari
   `env_file` atau dibiarkan — tidak dibaca lagi karena database tidak kosong.

Bila migrasi dilakukan ke volume yang **sudah** berisi `telegent.db`, impor
`.env` sengaja dilewati agar tidak menimpa setting yang sudah dikelola dari panel.
Dalam kasus itu isi manual lewat UI.

### Nama env yang berubah

| Lama | Sekarang | Catatan |
|---|---|---|
| `TELEGRAM_SESSION_DIR` | `TELEGENT_DATA_DIR` | Alias lama masih dibaca `Settings`, tetapi compose hanya memakai yang baru. |

---

## 5. Mode bot saja (`--no-web`)

Untuk container yang tidak butuh panel (CI, worker, migrasi sesi):

```bash
docker compose run --rm telegent --no-web
```

(`ENTRYPOINT` image sudah `telegent`, jadi cukup `--no-web` sebagai argumen.)

Perilaku identik dengan versi pra-web-panel: `Settings()` wajib valid, bot
langsung menyala, keluar dengan galat bila kredensial kurang. Berguna untuk
login Telegram interaktif sekali:

```bash
docker compose run --rm -it telegent --no-web
```

---

## 6. Mode fake (khusus pengujian)

`TELEGENT_FAKE=1` membuat bot dan klien Telegram menjadi tiruan: tidak ada
koneksi ke Telegram maupun Gemini, dan panggilan tiruan diterbitkan otomatis
untuk menguji UI Pemantauan beserta SSE-nya.

Aturan keamanannya:

- hanya nilai **tepat** `1` yang mengaktifkan — `true`, `yes`, `on` **tidak**;
- dibaca dari environment proses, **bukan** dari `.env`;
- selalu memunculkan peringatan di stderr dan di log saat aktif;
- terlihat di `GET /api/healthz` sebagai `"fake": true`.

```bash
TELEGENT_FAKE=1 docker compose up -d
curl -s http://127.0.0.1:8080/api/healthz   # {"fake": true, ...}
```

Kode OTP yang diterima mode fake: `12345`.

`TELEGENT_IGNORE_DOTENV=1` juga dipasang oleh runner E2E: tanpa itu, `.env` di
root repo ikut terimpor ke database pengujian dan skenario "panel kosong" tidak
pernah benar-benar teruji. Environment proses tetap dipakai — yang diabaikan hanya
berkas `.env`.

Menjalankan E2E secara lokal:

```bash
cd frontend
npx playwright install chromium   # sekali saja
npm run test:e2e                  # server + build ditangani `webServer`
npm run test:e2e:ui               # mode interaktif
```

Server E2E memakai direktori data `.e2e-data/` di root repo yang **selalu
dihapus** sebelum start, jadi setiap berjalan mulai dari kondisi kosong. Artefak
laporan ada di `frontend/playwright-report/` dan `frontend/test-results/`.

Lihat [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) untuk
persis langkah yang dijalankan di CI.

---

## 7. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `docker compose up` selesai, panel refused | `TELEGENT_HOST` di dalam container harus `0.0.0.0`, bukan `127.0.0.1`. |
| Runtime `not_configured` | Kredensial belum diisi di panel. Bot ditolak sampai lengkap. |
| Runtime `needs_login` | Berkas `*.session` belum ada. Login Telegram dari panel. |
| Panggilan masuk tapi tidak ada suara | P2P butuh UDP keluar. Coba `network_mode: host`. |
| Secret tersimpan tidak terbaca | `.secret_key` berubah atau hilang. Isi ulang kredensial dari panel. |
| Panel lambat dibuka | Level log `DEBUG` membebani stream log; turunkan di halaman Pengaturan. |