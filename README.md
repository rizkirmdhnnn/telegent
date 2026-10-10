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

Prinsip:
- **Banyak panggilan bersamaan** — semua state bersifat per-`CallSession` (tidak ada global mutable).
- **Seam untuk testability** — `protocols.AudioSink` dan `protocols.LiveVoiceSession`
  memungkinkan komponen inti diuji dengan fake tanpa jaringan/native.
- **Audio mulus** — frame dikirim pada cadence tetap 10 ms; saat tidak ada audio AI,
  dikirim frame senyap (mencegah jitter-buffer underrun).

Detail lebih lanjut: [`docs/architecture.md`](docs/architecture.md).

---

## Setup Lokal

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # atau: pip install -e .
cp .env.example .env             # isi TELEGRAM_API_ID/HASH & GEMINI_API_KEY
```

Jalankan:

```bash
python -m telegent               # atau: telegent
```

Saat pertama kali, Pyrogram meminta nomor telepon & kode OTP secara interaktif di terminal.
Telepon akun Telegram tersebut untuk menguji percakapan.

---

## Setup Docker

Login Telegram **sekali** (interaktif) agar file sesi tersimpan di volume `./data`:

```bash
mkdir -p data
docker compose run --rm telegent        # ikuti prompt login sekali
```

Setelah sesi ada, jalankan sebagai service:

```bash
docker compose up -d
docker compose logs -f
```

Catatan:
- File `*.session` disimpan di volume `./data` (bertahan antar restart).
- Panggilan P2P butuh UDP keluar; mode bridge umumnya cukup. Bila media tidak
  tersambung, aktifkan `network_mode: host` di `docker-compose.yml`.

---

## Konfigurasi (`.env`)

| Variabel | Default | Keterangan |
|---|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | — | Wajib (dari my.telegram.org) |
| `GEMINI_API_KEY` | — | Wajib (Google AI Studio) |
| `TELEGRAM_SESSION_NAME` | `userbot_session` | Nama file sesi (tanpa `.session`) |
| `TELEGRAM_SESSION_DIR` | `.` | Direktori sesi (`/data` di Docker) |
| `GEMINI_MODEL` | `gemini-3.1-flash-live-preview` | Model Live API |
| `ALLOWED_USER_IDS` | *(kosong = semua)* | Whitelist ID Telegram, pisah koma |
| `MAX_CONCURRENT_CALLS` | `4` | Batas panggilan bersamaan |
| `LOG_LEVEL` | `INFO` | Level logging |
| `SYSTEM_INSTRUCTION` / `GREETING_PROMPT` | *(default di kode)* | Persona & sapaan |

CLI opsional: `--allow-user <id>` (boleh berulang), `--log-level`.

---

## Tool Calling

Tool didaftarkan di `telegent.app.TelegentApp` (lihat `ai/tools/builtin.py`).
Tool bawaan saat ini: `get_current_datetime`.

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
pytest -q                 # unit + integration (dengan fake, tanpa jaringan)
pyright src/telegent      # type checking
```

---

## Struktur Proyek

```
src/telegent/               # paket utama
tests/                      # unit + integration test (fake)
scripts/                    # PoC/manual check lama (gemini_poc, telegram_voip, call_debugger)
docs/                       # dokumentasi
Dockerfile, docker-compose.yml
pyproject.toml
```

---

## Lisensi & Komponen

- `ntgcalls`: LGPL/GPL · `pyrogram`: LGPLv3 · `google-genai`: Apache-2.0.
