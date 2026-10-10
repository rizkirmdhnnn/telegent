# Arsitektur Telegent

## Gambaran

Telegent menerima panggilan Telegram 1-on-1, menjembatani audio ke **Gemini Live API**
dua arah, dan mengirim balik suara AI ke penelpon. Satu instance `CallSession`
menangani satu panggilan, sehingga banyak panggilan dapat berjalan bersamaan.

## Alur Panggilan

```
Penelpon            Telegram Server            Telegent (pyrogram + ntgcalls)        Gemini Live
   |                     |                              |                              |
   |--- panggil -------->|                              |                              |
   |                     |--- PhoneCallRequested ------>| ReceivedCall + AcceptCall    |
   |<-- dering ----------|                              | create_p2p_call + DH         |
   |--- ConfirmCall ---->|                              |                              |
   |                     |--- PhoneCall (aktif) ------->| exchange_keys + connect_p2p  |
   |                     |                              | set_stream_sources CAP+PLAY  |
   |<===== media WebRTC (audio 48 kHz mono) ===========>|                              |
   |                     |                              |--- audio 16 kHz ------------>|
   |                     |                              |<-- audio 24 kHz (jawaban) ---|
   |<===== audio 48 kHz ==|==============================|                              |
```

## Modul

### `config.py`
`Settings` (pydantic-settings): semua konfigurasi runtime, dibaca dari env/.env,
dengan validasi & properti turunan (`allowed_user_id_set`, `tg_frame_bytes`, `session_workdir`).

### `audio/`
- `resampler.py` — 48k↔16k (Turun) dan 24k↔48k (Naik).
- `framing.py` — `PcmFramer`: memecah aliran PCM menjadi frame berukuran tetap, sisa disimpan.
- `cadence.py` — `Cadence` (pacing deadline absolut) dan `run_cadence_sender`:
  mengirim satu frame tiap interval; bila antrean kosong → **frame senyap** (anti-stutter).

### `telegram/`
- `signaling.py` — konversi `RTCServer`/`PhoneCallProtocol`; `SignalingService`
  mengirim data signaling dengan retry `CALL_NOT_ACTIVE` dan penahanan sebelum call aktif.
- `media.py` — `NtgAudioSink` (implementasi `AudioSink`) + `external_audio_media`.
- `call_session.py` — `CallSession`: state machine + 3 worker (pengirim ke Gemini,
  penerima dari Gemini, pengirim ke Telegram) + eksekusi tool.

### `ai/`
- `events.py` — event netral (`AudioOut`, `TranscriptIn/Out`, `Interrupted`,
  `TurnComplete`, `ToolCallEvent`, `ToolCallCancelled`) agar inti tak bergantung tipe Gemini.
- `live_session.py` — `GeminiLiveSession`: membungkus SDK; `events()` memanggil ulang
  `receive()` per giliran (penting: SDK berhenti tiap `turn_complete`).
- `tools/` — `ToolRegistry` (deklarasi ke Gemini + eksekusi dengan timeout),
  `ToolSpec`, `builtin.py`.

### `app.py`
`TelegentApp`: membuat klien, mendaftarkan callback ntgcalls & handler update MTProto,
mengatur whitelist & batas konkurensi, membuka `CallSession` per panggilan, dan
menangani shutdown (SIGINT/SIGTERM).

## Keputusan Desain

| Masalah | Keputusan |
|---|---|
| `receive()` SDK berhenti tiap giliran | Loop luar memanggil ulang `receive()` di `GeminiLiveSession.events()` |
| Audio tersendat | Cadence 10 ms tetap + pengisian senyap; antrean besar, tanpa buang frame |
| `CALL_NOT_ACTIVE` | Tahan data signaling sampai call aktif, lalu flush; retry singkat |
| Banyak panggilan | Semua state per-`CallSession`; `ntgcalls` callback dispatch per `user_id` |
| Anti-penyalahgunaan | Whitelist + `MAX_CONCURRENT_CALLS` + rate-limit per pengguna (`rate_limit.CallRateLimiter`) + `MAX_CALL_DURATION` (watchdog di `CallSession`) |
| Anti-idle | Penelpon diam → AI konfirmasi; tetap tanpa respons → ucapkan pamitan lalu akhiri otomatis (lihat bawah) |
| Testability | Seam `AudioSink` / `LiveVoiceSession` + fake di `tests/helpers.py` |

## Anti-idle (Penelpon Tidak Menjawab)

Watchdog per sesi (`CallSession._idle_watchdog`) menjaga panggilan agar tidak menggantung:

1. **Deteksi aktivitas penelpon** dari event yang sudah ada: `TranscriptIn`
   (ucapan tertranskripsi) dan `Interrupted` (barge-in) → mereset timer
   (`_note_caller_activity`).
2. **Diam ≥ `IDLE_PROMPT_SECONDS`** (dan AI sudah selesai bicara, antrean audio
   kosong, tidak ada tool berjalan) → AI **mengonfirmasi** ("masih di sana?")
   lewat `LiveVoiceSession.send_prompt`.
3. **Tanpa respons ≥ `IDLE_HANGUP_SECONDS`** setelah konfirmasi → AI diminta
   mengucapkan **pamitan singkat**, lalu `schedule_hangup(min_wait=...)` menutup
   panggilan setelah audio selesai diputar.

Ambang dikonfigurasi via `IDLE_ENABLED`, `IDLE_PROMPT_SECONDS`,
`IDLE_HANGUP_SECONDS`. Bila penelpon kembali bersuara, status konfirmasi direset
sehingga siklus dapat berulang.

## Threading

Callback `ntgcalls` berjalan di thread native dan di-dispatch ke event loop asyncio
utama (`run_coroutine_threadsafe` / `call_soon_threadsafe`). Semua state panggilan
hanya disentuh dari loop tersebut.
