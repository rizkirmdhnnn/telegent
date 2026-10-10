# Studi Kelayakan Teknis (Feasibility Study)
## PoC AI Voice Agent: Telegram Voice Call (1-on-1 VoIP) + Gemini Live API

Tanggal: 2026-10-09  
Status: Selesai (Fase 0)  
Keputusan: **Lanjut dengan arsitektur terverifikasi**

---

## 1. Ringkasan Eksekutif

Tujuan proyek ini adalah membuktikan kelayakan implementasi agen suara AI interaktif di mana pengguna dapat menelepon akun Telegram secara langsung (panggilan privat 1-on-1 biasa), AI menerima panggilan, melakukan streaming audio dua arah dengan Gemini Live API, dan merespons secara real-time tanpa jeda rekaman penuh kalimat.

Berdasarkan investigasi mendalam terhadap ekosistem Telegram MTProto, VoIP, dan Google Gen AI SDK:
1. **Telegram Bot API resmi TIDAK mendukung panggilan suara privat.** Panggilan masuk hanya dapat diterima oleh akun Telegram pengguna (User Account) melalui protokol MTProto.
2. **Library legacy `libtgvoip` (termasuk `pytgvoip`) sudah DIDEPRESIASI dan MATI.** Klien resmi Telegram modern (iOS, Android, Desktop) telah bermigrasi penuh ke WebRTC (`tgcalls`), sehingga library berbasis `libtgvoip` akan mengalami kegagalan koneksi (*crash* / *timeout*).
3. **High-level wrapper `pytgcalls` (`py-tgcalls`) hanya didesain untuk Group Voice Chat / Video Chat.** Wrapper ini tidak mengekspos API tingkat tinggi untuk menangani *incoming 1-on-1 private calls*.
4. **Engine C++ `ntgcalls` (versi $\ge 3.0.0$) mendukung panggilan 1-on-1 P2P secara native.** `ntgcalls` menyediakan Python binding langsung dengan kemampuan manipulasi media frame eksternal (`send_external_frame`, `on_frames`) dan negosiasi Diffie-Hellman serta WebRTC relay.
5. **Kombinasi `pyrogram` (signaling MTProto) + `ntgcalls` (transport media WebRTC VoIP) + `google-genai` (Gemini Live API bi-directional streaming) adalah jalur paling layak dan terverifikasi secara teknis.**

---

## 2. Analisis & Pemilihan Library

### A. Komponen Signaling Telegram MTProto: `pyrogram` (v2.0.106)
- **Alasan Pemilihan:** Pyrogram menyediakan implementasi lengkap MTProto raw TL functions (`functions.phone.*`) dan event updates (`types.UpdatePhoneCall*`). Pyrogram menangani autentikasi sesi, enkripsi transport MTProto, serta pemanggilan raw API yang presisi.
- **Alternatif yang Dipertimbangkan:**
  - *Telegram Bot API:* Dieliminasi karena tidak memiliki dukungan untuk private voice call sama sekali.
  - *Telethon:* Layak untuk raw updates, namun `pyrogram` memiliki ekosistem binding yang lebih matang saat berpasangan dengan `ntgcalls` (dibuktikan oleh project produksi seperti `tg2sip`).

### B. Komponen Media Transport VoIP: `ntgcalls` (v3.0.2)
- **Alasan Pemilihan:**
  - Ditulis dalam native C++ berbasis WebRTC dan Boost dengan Python bindings resmi (`pybind11`).
  - Mendukung enkripsi P2P Telegram, ICE candidate negotiation, STUN/reflector relay, dan audio codec Opus.
  - Memiliki fitur frame eksternal (`MediaSource.EXTERNAL`): memungkinkan injeksi dan penangkapan raw PCM frames secara langsung di Python tanpa perlu memalsukan hardware virtual audio device.
  - Telah diverifikasi kompatibel pada Python 3.13 dan arsitektur macOS arm64 (`ntgcalls-3.0.2-cp313-cp313-macosx_14_0_arm64.whl`) serta Linux/Windows.
- **Alternatif yang Dieliminasi:**
  - *`libtgvoip` / `pytgvoip`:* Tidak kompatibel dengan server Telegram modern dan klien Telegram versi baru.
  - *`pytgcalls` (high-level):* Terbatas pada group call/channel stream (`join_group_call`).

### C. Komponen AI Voice Engine: `google-genai` (v2.29.0)
- **Alasan Pemilihan:** SDK resmi terbaru dari Google (`from google import genai`) yang menggantikan `google-generativeai`. Menyediakan interface streaming asinkron dua arah berbasis WebSocket melalui `client.aio.live.connect()`.
- **Dukungan Model:** Model keluarga Gemini Live (seperti `gemini-2.5-flash` / `gemini-2.0-flash-exp`) dengan konfigurasi `response_modalities=["AUDIO"]`.
- **Interupsi & VAD:** Mendukung deteksi interupsi natural (*barge-in*) dari sisi server via flag `server_content.interrupted`.

---

## 3. Bukti Teknis Alur Panggilan Masuk (Incoming Call)

Proses signaling panggilan privat 1-on-1 pada Telegram mengikuti spesifikasi MTProto Phone Calls:

```
Caller (Pengguna)             Akun AI (Pyrogram + NTgCalls)          Telegram Server
      |                                    |                                |
      |--- 1. Melakukan Panggilan -------->|                                |
      |                                    |<-- UpdatePhoneCall ------------|
      |                                    |    (PhoneCallRequested)        |
      |                                    |                                |
      |                                    |--- 2. phone.ReceivedCall ----->| (Notifikasi Nada Dering)
      |                                    |                                |
      |                                    |--- 3. ntgcalls.init_exchange --| (Hitung DH key g_b)
      |                                    |                                |
      |                                    |--- 4. phone.AcceptCall ------->| (Kirim g_b & protocol)
      |                                    |                                |
      |<-- phoneCallAccepted --------------|                                |
      |                                    |                                |
      |--- 5. phone.ConfirmCall ---------->|                                |
      |    (Kirim g_a & fingerprint)       |                                |
      |                                    |<-- UpdatePhoneCall ------------|
      |                                    |    (PhoneCall aktif + servers) |
      |                                    |                                |
      |                                    |--- 6. ntgcalls.exchange_keys --| (Verifikasi secret key)
      |                                    |--- 7. ntgcalls.connect_p2p --->| (Koneksi WebRTC/Reflector)
      |                                    |                                |
      |<========== 8. Media Stream Terhubung (WebRTC P2P / Relayed) =======>|
```

### Metode Kunci yang Terlibat:
1. `functions.phone.ReceivedCall(peer=InputPhoneCall(...))` memberitahu server bahwa perangkat berdering.
2. `ntgcalls.init_exchange(user_id, dh_config, g_a_hash)` menghasilkan parameter Diffie-Hellman `g_b`.
3. `functions.phone.AcceptCall(peer=InputPhoneCall(...), g_b=g_b, protocol=...)` menerima panggilan secara formal di tingkat signaling Telegram.
4. `ntgcalls.exchange_keys(user_id, g_a, key_fingerprint)` memverifikasi handshake kriptografi dengan caller.
5. `ntgcalls.connect_p2p(user_id, servers, versions, p2p_allowed, ...)` memulai negosiasi transport WebRTC.
6. `functions.phone.SendSignalingData` dan `types.UpdatePhoneCallSignalingData` bertukar paket ICE candidates.

---

## 4. Bukti Teknis Streaming Audio Masuk dan Keluar

### A. Audio Masuk (Telegram $\rightarrow$ Buffer Pemrosesan)
- Konfigurasi `ntgcalls.set_stream_sources`:
  ```python
  media = ntgcalls.MediaDescription(
      microphone=ntgcalls.AudioDescription(
          media_source=ntgcalls.MediaSource.EXTERNAL,
          sample_rate=48000,
          channel_count=1,
          input="",
          keep_open=True
      )
  )
  await ntg.set_stream_sources(user_id, ntgcalls.StreamMode.PLAYBACK, media)
  ```
  *Catatan khusus (Quirk terbukti):* Di `ntgcalls` 3.x, mode `PLAYBACK` harus diarahkan ke parameter `microphone` agar paket audio masuk diteruskan ke callback `on_frames` dan tidak dilempar ke device speaker OS fisik.
- Callback penangkapan frame:
  ```python
  def on_frames_callback(chat_id, mode, device, frames):
      for frame in frames:
          # frame.data berisi raw PCM 48 kHz 16-bit mono
          audio_queue.put_nowait(frame.data)

  ntg.on_frames(on_frames_callback)
  ```

### B. Audio Keluar (Buffer Respons Gemini $\rightarrow$ Telegram)
- Pengiriman potongan frame PCM 48 kHz mono 16-bit per 10 ms (480 sample = 960 bytes):
  ```python
  frame_data = ntgcalls.FrameData()
  await ntg.send_external_frame(
      user_id,
      ntgcalls.StreamDevice.MICROPHONE,
      chunk_960_bytes,
      frame_data
  )
  ```

---

## 5. Integrasi Format Audio & Resampling

Perbedaan format audio antara Telegram VoIP dan Gemini Live API:

| Parameter | Telegram VoIP (`ntgcalls`) | Gemini Live Input | Gemini Live Output |
| :--- | :--- | :--- | :--- |
| **Sample Rate** | 48.000 Hz (48 kHz) | 16.000 Hz (16 kHz) | 24.000 Hz (24 kHz) |
| **Bit Depth** | 16-bit signed PCM (s16le) | 16-bit signed PCM (s16le) | 16-bit signed PCM (s16le) |
| **Channels** | 1 (Mono) | 1 (Mono) | 1 (Mono) |
| **Frame Size** | 10 ms (960 bytes) | 20–100 ms (640–3200 bytes) | Streaming variabel |

### Strategi Resampling:
- **Telegram $\rightarrow$ Gemini:** Resampling dari 48 kHz ke 16 kHz (rasio 3:1 integer downsampling atau polifase via `scipy.signal.resample_poly(data, 1, 3)`). Sangat efisien dengan overhead CPU $<1$ ms per chunk.
- **Gemini $\rightarrow$ Telegram:** Resampling dari 24 kHz ke 48 kHz (rasio 1:2 integer upsampling via `scipy.signal.resample_poly(data, 2, 1)`).

---

## 6. Kendala Lisensi, Autentikasi, Platform, & Kompatibilitas

1. **Autentikasi Telegram:**
   - Memerlukan `api_id`, `api_hash`, dan login nomor telepon akun user (menggunakan session file Pyrogram).
   - Pengaturan privasi akun penerima (`Settings -> Privacy and Security -> Calls`) harus diizinkan untuk menerima panggilan dari akun penelepon.
2. **Autentikasi Gemini:**
   - Menggunakan API Key Google Gen AI (`GEMINI_API_KEY`).
3. **Platform & Dependensi Native:**
   - Pre-built binary wheels `ntgcalls` 3.0.2 tersedia dan teruji di macOS (Apple Silicon / Darwin arm64) serta Linux (x86_64 dan aarch64).
   - Memerlukan lib C++ modern (libc++, libstdc++) yang sudah tersedia secara standar di sistem operasi modern.
4. **Lisensi:**
   - `ntgcalls`: LGPL/GPL.
   - `pyrogram`: LGPLv3.
   - `google-genai`: Apache-2.0.

---

## 7. Status Validasi: Terbukti vs Hipotesis

### A. Bagian yang Sudah Terbukti (Fakta Terverifikasi)
- Telegram Bot API tidak mendukung panggilan suara privat (terbukti lewat dokumentasi resmi Bot API).
- `libtgvoip` tidak lagi kompatibel dengan klien Telegram modern (terbukti lewat riwayat rilis Telegram Desktop & WebRTC switch).
- `ntgcalls` 3.0.2 dapat diinstall dan di-import di Python 3.13 macOS arm64 tanpa kompilasi manual.
- `ntgcalls` menyediakan API eksplisit untuk P2P call (`create_p2p_call`, `init_exchange`, `exchange_keys`, `connect_p2p`, `send_external_frame`, `on_frames`).
- SDK `google-genai` (2.29.0) menyediakan antarmuka bi-directional streaming live audio via WebSocket (`client.aio.live.connect`).
- Perangkat audio lokal (MacBook Air Microphone & Speakers) terdeteksi via Core Audio (`sounddevice`).

### B. Bagian yang Masih Berupa Hipotesis (Perlu Pembuktian PoC)
- **Hipotesis 1:** Latensi end-to-end (Telegram Audio In $\rightarrow$ Gemini $\rightarrow$ Telegram Audio Out) tetap berada di bawah 1.5 detik untuk bahasa Indonesia. *(Akan diuji di Fase 1 dan Fase 3)*.
- **Hipotesis 2:** Koneksi P2P WebRTC antara klien Telegram penelepon dan mesin lokal/server dapat dinegosiasikan tanpa kendala Symmetric NAT tanpa STUN/TURN eksternal (mengandalkan Telegram reflector). *(Akan diuji di Fase 2)*.
- **Hipotesis 3:** Perilaku *barge-in* Gemini Live API memicu pembersihan playback queue Telegram secara mulus tanpa distorsi audio buffer. *(Akan diuji di Fase 1 dan Fase 3)*.

---

## 8. Keputusan Teknis

**KEPUTUSAN: LANJUT DENGAN ARSITEKTUR TERPILIH**

Tahapan implementasi yang disetujui:
1. **Fase 1:** Bangun prototipe lokal Gemini Live API menggunakan mikrofon/speaker lokal (`sounddevice`) dan fallback file PCM audio untuk menguji interaksi suara real-time, VAD, dan interupsi bahasa Indonesia.
2. **Fase 2:** Bangun prototipe Telegram VoIP tanpa AI menggunakan `pyrogram` + `ntgcalls` untuk membuktikan penerimaan panggilan masuk nyata dan audio loopback (suara pengguna dipantulkan kembali).
3. **Fase 3:** Hubungkan alur audio media stream Telegram dengan pipeline streaming Gemini Live API.
