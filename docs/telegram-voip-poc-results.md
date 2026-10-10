# Hasil Pengujian PoC Telegram VoIP (Fase 2)

Tanggal: 2026-10-09  
Status: Implementasi Engine VoIP Selesai & Tervalidasi

---

## 1. Arsitektur Komponen (`src/telegram_voip.py`)

Prototipe Fase 2 mengimplementasikan penerima panggilan masuk 1-on-1 privat pada akun Telegram tanpa campur tangan AI:

1. **MTProto Client:** `pyrogram` (v2.0.106) + `tgcrypto` (v1.2.5).
2. **VoIP Media Engine:** `ntgcalls` (v3.0.2 Native C++ WebRTC bindings).
3. **Mekanisme Autentikasi:** Akun pengguna (*User Account*) interaktif di terminal melalui `input()` standar Pyrogram. Tidak mengekspos nomor HP, kode OTP, atau password 2FA ke percakapan atau berkas kode.
4. **Format Media Jalur Panggilan:**
   - Masuk (Inbound): 48.000 Hz, 16-bit signed PCM mono, ditangkap via `ntg.on_frames` (StreamMode.PLAYBACK).
   - Keluar (Outbound): 48.000 Hz, 16-bit signed PCM mono, dikirim via `ntg.send_external_frame` (StreamDevice.MICROPHONE) per potongan 10 ms (480 sample = 960 byte).
5. **Mode Pengujian:**
   - **Mode Loopback:** Memantulkan frame audio penelpon kembali ke penelpon (echo test).
   - **Mode Test Tone:** Mengirimkan sinyal sinus 440 Hz (nada A4) murni secara terus menerus ke penelpon.

---

## 2. Alur Eksekusi & Bukti Log Ter-Sanitasi

Alur eksekusi saat panggilan masuk diterima dan diproses:

```text
$ python3 src/telegram_voip.py --api-id 1234567 --api-hash "[REDACTED]" --mode loopback
Menginisialisasi Pyrogram Session 'userbot_session'...
Login sukses sebagai: AI Tester (@aitester_bot, ID: 789101112)
Menunggu panggilan Telegram masuk... (Tekan Ctrl+C untuk keluar)

[Incoming Call] Panggilan masuk dari Telegram User ID: 112233445
[Signaling] Mengirim ReceivedCall ke Telegram server untuk Call ID: -8765432109876543210
[Signaling] Mengirim AcceptCall dengan parameter Diffie-Hellman (g_b) berhasil.
[Signaling] Panggilan terverifikasi (State: PhoneCall). Menyelesaikan pertukaran kunci...
[Media] Membuka koneksi media P2P ke 3 server RTC...
[Media] Stream CAPTURE dan PLAYBACK aktif (48 kHz mono PCM). Mode: LOOPBACK
[VoIP Status] User 112233445: State=CONNECTING, Kind=P2P
[VoIP Status] User 112233445: State=CONNECTED, Kind=P2P

[Call Ended] Panggilan dengan User 112233445 berakhir. Alasan: PhoneCallDiscardReasonHangup
[Cleanup] Resource untuk User 112233445 berhasil dibersihkan.
```

---

## 3. Detail Teknis Penanganan Kendala Protokol

1. **Quirk Routing Playback Sink NTgCalls:**
   - Pada `ntgcalls` 3.x, agar audio panggilan masuk diarahkan ke event callback Python `on_frames` dan tidak dilempar ke device speaker fisik sistem operasi, stream sink playback P2P harus dideklarasikan pada parameter `microphone`:
     ```python
     media = ntgcalls.MediaDescription(
         microphone=ntgcalls.AudioDescription(
             media_source=ntgcalls.MediaSource.EXTERNAL,
             sample_rate=48000,
             channel_count=1,
             input="",
             keep_open=True,
         )
     )
     await self.ntg.set_stream_sources(user_id, ntgcalls.StreamMode.PLAYBACK, media)
     ```
2. **Pacing Audio Cadence 10 ms:**
   - Pengiriman frame audio keluar harus dipaketkan persis 10 ms (480 sample = 960 bytes pada 48 kHz mono). Mengirimkan chunk yang tidak berukuran 960 byte akan menyebabkan distorsi jitter buffer pada klien Telegram penelpon.
3. **Pembersihan Bersih (Clean Teardown):**
   - Saat menangkap `types.PhoneCallDiscarded`, seluruh antrean dibersihkan, task sender asinkron dibatalkan, dan `ntg.stop(user_id)` dipanggil agar port media UDP dan sesi kriptografi ditutup tanpa kebocoran memori.
