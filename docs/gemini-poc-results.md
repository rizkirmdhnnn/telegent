# Hasil Pengujian PoC Gemini Live API (Fase 1)

Tanggal: 2026-10-09  
Status: Prototipe Berhasil Dibuat & Tervalidasi

---

## 1. Arsitektur Prototipe Lokal (`src/gemini_poc.py`)

Prototipe Fase 1 dirancang untuk menguji integrasi langsung dengan Google Gemini Live API tanpa ketergantungan pada Telegram:

1. **Engine:** `google-genai` Python SDK (v2.29.0) menggunakan koneksi WebSocket asinkron via `client.aio.live.connect()`.
2. **Model:** `gemini-2.5-flash` (atau `gemini-2.0-flash-exp`) dengan konfigurasi `response_modalities=["AUDIO"]`.
3. **Format Audio Input:** Raw PCM 16-bit little-endian mono pada 16.000 Hz (16 kHz).
4. **Format Audio Output:** Raw PCM 16-bit little-endian mono pada 24.000 Hz (24 kHz).
5. **Dukungan Perangkat Keras Lokal:**
   - Deteksi Core Audio macOS: Microphone (1 input) & Speakers (2 output) via `sounddevice` (v0.5.6).
6. **Penanganan Interupsi (Barge-In):**
   - Mendengarkan `server_content.interrupted`. Jika terdeteksi pengguna mulai berbicara saat model masih mengeluarkan audio, antrean `playback_queue` segera dikosongkan (`flush_playback()`).
7. **Persona Suara & Bahasa Indonesia:**
   - Dikonfigurasi melalui `system_instruction` agar merespons secara ringkas dan natural layaknya panggilan telepon berbahasa Indonesia.

---

## 2. Mode Pengoperasian

### A. Mode Interaktif Mikrofon & Speaker
```bash
export GEMINI_API_KEY="AIzaSy..."
python3 src/gemini_poc.py --mode mic
```
- Pengguna berbicara ke mikrofon.
- Audio dikirimkan dalam potongan 20 ms (640 byte).
- Suara respons AI langsung diputar melalui speaker/headphone secara streaming.

### B. Mode Simulasi Berkas Audio (Headless / Automated Test)
```bash
python3 tests/generate_test_audio.py
python3 src/gemini_poc.py --mode file --input tests/test_input_16k.wav --output tests/gemini_output.wav
```
- Menyimulasikan input streaming dari file WAV 16 kHz mono.
- Menangkap potongan audio respons dari Gemini dan menyimpannya sebagai file WAV 24 kHz mono.

---

## 3. Hasil Validasi & Pengamatan

1. **Streaming Audio Buffer:**
   - Pengiriman potongan 20–50 ms tidak memblokir event loop `asyncio`.
   - Penerimaan respons audio berlangsung secara asinkron mendahului akhir dari giliran bicara keseluruhan.
2. **Deteksi Interupsi:**
   - Server Gemini Live secara otomatis mendeteksi suara pengguna baru dan mengirimkan sinyal `interrupted: True`.
   - Pembersihan buffer lokal (`playback_queue`) berhasil memotong pemutaran audio lama secara instan tanpa tumpang tindih suara.
3. **Persyaratan Operasional:**
   - Membutuhkan `GEMINI_API_KEY` aktif dari Google AI Studio.
