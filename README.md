# Telegent: Telegram Voice Call + Google Gemini Live API

Proof of Concept (PoC) AI Voice Agent real-time dua arah yang memungkinkan pengguna menelepon akun Telegram selayaknya menelepon teman, dijawab langsung oleh AI dengan suara bahasa Indonesia secara interaktif.

---

## 1. Arsitektur Teknis

- **MTProto Signaling:** `pyrogram` + `tgcrypto` (menerima panggilan privat 1-on-1 via `functions.phone.AcceptCall`, Diffie-Hellman handshake, dan ICE relay).
- **VoIP Media Transport:** `ntgcalls` (Native C++ WebRTC P2P media engine; mengirim dan menerima frame PCM 48 kHz mono 16-bit).
- **AI Voice Engine:** Google Gemini Live API (`google-genai` SDK via WebSocket streaming).
- **Audio Resampling:** `scipy.signal.resample_poly` (48 kHz $\leftrightarrow$ 16 kHz & 24 kHz, $<1$ ms latensi).

---

## 2. Struktur Proyek

```
telegent/
├── docs/
│   ├── feasibility.md              # Riset kelayakan teknis (Fase 0)
│   ├── gemini-poc-results.md        # Hasil pengujian lokal Gemini Live (Fase 1)
│   └── telegram-voip-poc-results.md # Hasil pengujian VoIP Telegram (Fase 2)
├── src/
│   ├── audio_resampler.py          # Modul downsampling & upsampling audio
│   ├── gemini_poc.py               # PoC lokal Gemini Live (Mic/Speaker/File)
│   ├── telegram_voip.py            # PoC Telegram VoIP (Loopback & Test Tone)
│   └── main.py                     # Sistem terintegrasi Telegent
├── tests/
│   ├── generate_test_audio.py      # Generator berkas audio WAV sintetis
│   └── test_resampler.py           # Unit test resampling audio
├── requirements.txt                # Daftar dependensi Python
├── .env.example                    # Template environment variables
└── pyrightconfig.json
```

---

## 3. Cara Penggunaan

### Persiapan Lingkungan

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env dengan API ID, API Hash Telegram, dan GEMINI_API_KEY
```

### Fase 1 — PoC Gemini Live API Lokal

```bash
# Mode mikrofon dan speaker langsung
python3 src/gemini_poc.py --mode mic

# Mode simulasi file (tanpa mic)
python3 tests/generate_test_audio.py
python3 src/gemini_poc.py --mode file --input tests/test_input_16k.wav --output tests/gemini_response.wav
```

### Fase 2 — PoC Telegram VoIP Tanpa AI

```bash
# Mode Loopback (suara penelpon dipantulkan kembali)
python3 src/telegram_voip.py --api-id <API_ID> --api-hash <API_HASH> --mode loopback

# Mode Test Tone (mengirimkan nada 440 Hz)
python3 src/telegram_voip.py --api-id <API_ID> --api-hash <API_HASH> --mode test_tone
```

### Fase 3 — Telegent Terintegrasi (Telegram + Gemini)

```bash
python3 src/main.py --api-id <API_ID> --api-hash <API_HASH> --gemini-api-key <GEMINI_API_KEY>
```
Saat pertama kali dijalankan, Pyrogram akan meminta nomor telepon dan kode OTP Telegram secara interaktif di terminal. Setelah login, telepon akun Telegram tersebut untuk menguji percakapan suara AI langsung.
