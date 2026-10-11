# Telegent

AI voice agent real-time: pengguna menelepon akun Telegram (panggilan privat 1-on-1),
dijawab otomatis oleh AI dengan suara bahasa Indonesia, mendukung **tool calling**.

Dibangun di atas `pyrogram` (signaling MTProto) + `ntgcalls` (media WebRTC) +
**Google Gemini Live API** (`google-genai`).

---

## Arsitektur

| Lapisan | Modul | Peran |
|---|---|---|
| Konfigurasi | `telegent.config` | `Settings` tervalidasi dari env/.env |
| Audio | `telegent.audio.{resampler,framing,cadence}` | Resampling, framing 10 ms, pacing cadence-stabil |
| Telegram | `telegent.telegram.{signaling,media,call_session}` | Signaling panggilan, media ntgcalls, state machine per panggilan |
| AI | `telegent.ai.{live_session,prompt,events}` | Sesi Gemini Live + event netral |
| Tool | `telegent.ai.tools.{spec,registry,builtin}` | Deklarasi + eksekusi tool |
| Orkestrasi | `telegent.app` | Klien Telegram, dispatch panggilan, batas konkurensi |
| Web panel | `telegent.web.*` | FastAPI + SPA, autentikasi, penyimpanan setting, kontrol runtime, pemantauan |

Prinsip:
- **Banyak panggilan bersamaan** — semua state bersifat per-`CallSession` (tidak ada global mutable).
- **Seam untuk testability** — `protocols.AudioSink` dan `protocols.LiveVoiceSession`
  memungkinkan komponen inti diuji dengan fake tanpa jaringan/native.
- **Audio mulus** — frame dikirim pada cadence tetap 10 ms; saat tidak ada audio AI,
  dikirim frame senyap (mencegah jitter-buffer underrun).

Detail lebih lanjut: [`docs/architecture.md`](docs/architecture.md).

**Web panel.** Semua dipaketkan dalam satu proses: panel FastAPI + bot pada event
loop yang sama. Bot start/stop/restart lewat UI **tidak** mematikan panel.

---

## Setup Lokal (uv)

Proyek memakai [uv](https://docs.astral.sh/uv/) untuk mengelola dependensi & lingkungan
(konfigurasi ada di `pyproject.toml`, versi terkunci di `uv.lock`).

```bash
uv sync                    # buat .venv sesuai uv.lock (dev group terpasang)
uv sync --extra poc        # opsional: + sounddevice (mic/speaker untuk PoC lokal)
```

### Mode panel (default)

```bash
uv run telegent            # panel web + bot; buka http://127.0.0.1:8080
```

Tidak perlu `.env`: panel boot tanpa kredensial, lalu Anda buat akun admin dan
mengisi kredensial dari UI. Konfigurasi tersimpan di database
(`data/telegent.db`), bukan di environment.

Butuh SPA yang sudah dibangun agar UI tampil (bukan halaman placeholder):

```bash
cd frontend && npm install && npm run build && cd ..
```

Opsi: `--host`, `--port`, `--log-level`.

### Mode bot saja (headless)

```bash
cp .env.example .env       # isi TELEGRAM_API_ID/HASH & GEMINI_API_KEY
uv run telegent --no-web   # atau: uv run python -m telegent --no-web
```

Perilaku identik dengan versi sebelum web panel: kredensial wajib dari
environment, Pyrogram meminta nomor telepon & kode OTP secara interaktif di
terminal. Telepon akun Telegram tersebut untuk menguji percakapan.

---

## Setup Docker

Satu image, satu service. Image dibangun multi-stage: tahap Node membangun SPA,
tahap Python menyalin hasilnya; **image akhir tidak memuat Node**.

```bash
mkdir -p data
docker compose up -d
docker compose logs -f
```

Buka **http://127.0.0.1:8080**. Login Telegram dilakukan dari panel, bukan dari
terminal — jadi `docker compose run` untuk login interaktif tidak lagi diperlukan
(masih tersedia lewat `--no-web` bila diperlukan).

Catatan:
- Seluruh state ada di volume `./data`: `telegent.db`, `.secret_key`, `*.session`.
- Port dipetakan ke loopback host saja (`127.0.0.1:8080`); akses jarak jauh lewat
  SSH tunnel / VPN.
- Panggilan P2P butuh UDP keluar; mode bridge umumnya cukup. Bila media tidak
  tersambung, aktifkan `network_mode: host` di `docker-compose.yml`.

Panduan lengkap (deploy, backup, migrasi dari `.env` lama, mode fake):
[`docs/web-panel/deployment.md`](docs/web-panel/deployment.md).

---

## Konfigurasi

Dua kelompok, tergantung mode:

**Mode panel (default)** — konfigurasi disimpan di **database** dan dikelola dari
UI. Environment hanya untuk hal yang dibutuhkan sebelum DB siap (spec §3):

| Variabel | Default | Keterangan |
|---|---|---|
| `TELEGENT_DATA_DIR` | `./data` (`/data` di Docker) | Direktori DB, `*.session`, `.secret_key` |
| `TELEGENT_DB_URL` | `sqlite+aiosqlite:///<data_dir>/telegent.db` | URL database |
| `TELEGENT_SECRET_KEY` | *(kosong)* | Kunci Fernet; bila kosong dibuat di `data/.secret_key` |
| `TELEGENT_HOST` / `TELEGENT_PORT` | `127.0.0.1` / `8080` | Bind panel |
| `TELEGENT_SESSION_TTL_HOURS` | `168` | Umur cookie sesi admin |
| `TELEGENT_AUTOSTART_BOT` | `true` | Jalankan bot saat boot bila sudah siap |

**Mode `--no-web`** — konfigurasi dari environment/`.env` (lihat
[`.env.example`](.env.example)):

| Variabel | Default | Keterangan |
|---|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | — | Wajib (dari my.telegram.org) |
| `GEMINI_API_KEY` | — | Wajib (Google AI Studio) |
| `TELEGRAM_SESSION_NAME` | `userbot_session` | Nama file sesi (tanpa `.session`) |
| `TELEGENT_DATA_DIR` | `.` | Direktori sesi (alias lama: `TELEGRAM_SESSION_DIR`) |
| `GEMINI_MODEL` | `gemini-3.1-flash-live-preview` | Model Live API |
| `ALLOWED_USER_IDS` | *(kosong = semua)* | Whitelist ID Telegram, pisah koma |
| `MAX_CONCURRENT_CALLS` | `4` | Batas panggilan bersamaan |
| `MAX_CALL_DURATION` | `600` | Durasi maksimum 1 panggilan (detik); `0` = tanpa batas |
| `MAX_CALLS_PER_WINDOW` / `CALL_WINDOW_SECONDS` | `5` / `60` | Rate-limit per pengguna; `0` = tanpa batas |
| `LOG_LEVEL` | `INFO` | Level logging |
| `SYSTEM_INSTRUCTION` / `GREETING_PROMPT` | *(default di kode)* | Persona & sapaan |

Nilai `.env` lama **diimpor sekali** ke database saat panel pertama kali boot di
volume kosong, sehingga migrasi tidak perlu manual.

CLI: `--no-web`, `--host`, `--port`, `--log-level`, `--allow-user <id>`
(berlaku pada mode `--no-web`).

---

## Tool Calling

Tool didaftarkan di `telegent.app.TelegentApp` (lihat `ai/tools/builtin.py`).
Tool bawaan: `get_current_datetime` dan `end_call` (mengakhiri panggilan).

Menambah tool baru:

```python
from telegent.ai.tools.spec import ToolSpec, ToolContext

async def handler(ctx: ToolContext, args: dict) -> dict:
    return {"output": {...}}          # atau {"error": "..."} bila gagal

spec = ToolSpec(
    name="nama_tool",
    description="Dijelaskan ke model untuk memutuskan kapan memanggilnya.",
    parameters_json_schema={"type": "object", "properties": {...}},
    handler=handler,
    timeout=5.0,
    behavior="BLOCKING",              # atau "NON_BLOCKING"
)
```

Panduan lengkap: [`docs/tools.md`](docs/tools.md).

---

## Testing

```bash
uv run pytest -q                 # backend: unit + integrasi (fake, tanpa jaringan)
uv run pyright src/telegent      # type checking

cd frontend
npm install
npm run check                    # svelte-check
npm run test                     # unit test (Vitest)
npm run build                    # build SPA produksi
npm run test:e2e                 # Playwright (server & build ditangani otomatis)
```

E2E menjalankan proses Python sungguhan dalam mode tiruan (`TELEGENT_FAKE=1`):
tidak ada kredensial dan tidak ada koneksi ke Telegram/Gemini. Frontend memakai
cache browser di `~/.cache/ms-playwright`; jalankan `npx playwright install
chromium` sekali bila belum terpasang.

---

## Struktur Proyek

```
src/telegent/               # paket utama (bot + telegent.web untuk panel)
tests/                      # unit + integration test (fake)
frontend/                   # SPA SvelteKit 5 (Tailwind v4) + Vitest + Playwright
scripts/                    # utilitas manual (call_debugger, gemini_live_check)
docs/                       # dokumentasi (docs/web-panel/deployment.md untuk deploy)
.github/workflows/ci.yml    # CI (backend + frontend + e2e)
Dockerfile, docker-compose.yml
pyproject.toml, uv.lock
```

---

## Troubleshooting

- **Crash `SIGABRT` / "Abort trap: 6" saat program dimatikan (macOS).**
  Berasal dari destruktor statis `ntgcalls` (WebRTC C++) yang berjalan saat
  interpreter Python keluar (`__cxa_finalize`). Telegent sudah keluar lewat
  `os._exit()` untuk melewatinya — lihat `telegent/__main__.py::_exit_cleanly`.
  Ini normal dan tidak memengaruhi fungsionalitas.
- **Panel 502/refused setelah `docker compose up`.** `TELEGENT_HOST` di dalam
  container harus `0.0.0.0`; yang di-loopback adalah port di host.

---

## Lisensi

Kode proyek ini dilisensikan di bawah **MIT** — lihat [`LICENSE`](LICENSE).

Komponen pihak ketiga: `ntgcalls` (LGPL/GPL) · `pyrogram` (LGPLv3) · `google-genai` (Apache-2.0).
