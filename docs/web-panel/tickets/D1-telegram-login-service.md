# D1 — Layanan login Telegram programatik

- **Epic/Fase:** D / Fase 2
- **Dependensi:** A4, A7
- **Estimasi:** L
- **Referensi:** spec §8.4 · open-questions Q10/Q11

## Konteks
Login Telegram saat ini interaktif lewat stdin Pyrogram. Kita perlu alur programatik:
kirim kode → verifikasi → (bila perlu) password 2FA, lalu simpan sesi.

## Tujuan
- `TelegramLoginService` yang mengelola klien tak-terautentikasi & state login
  (`send_code`, `sign_in`, `check_password`).
- Penanganan error eksplisit: `PhoneNumberInvalid`, `PhoneCodeInvalid`,
  `PhoneCodeExpired`, `SessionPasswordNeeded`, `FloodWait`.
- Setelah sukses: sesi tersimpan di `TELEGENT_DATA_DIR`; update `telegram_account`.

## Deliverable
- `src/telegent/web/telegram_login.py`
- Skema/state `login_flow` (A2)

## Langkah implementasi
1. Bangun `Client` dengan api_id/hash dari store, session name & workdir dari data dir.
2. `start(phone)`: `send_code` → simpan `phone_code_hash` + `expires_at` → flow `code_sent`.
3. `verify(code)`: `sign_in`; bila `SessionPasswordNeeded` → flow `awaiting_password`.
4. `password(pwd)`: `check_password` → sukses → `telegram_account.status=logged_in`
   + `get_me()` untuk user_id/username.
5. `logout()`: `log_out` pada klien + hapus berkas sesi + status `logged_out`.
6. Tangani `FloodWait` → kembalikan `retry_after`; redaksi apa pun yang sensitif.
7. Bersihkan `login_flow` kedaluwarsa (TTL ~10 menit).

## Kriteria terima (Definition of Done)
- [ ] Alur sukses (fake Pyrogram) menghasilkan status `logged_in` + data user.
- [ ] `SessionPasswordNeeded` beralih ke langkah password dan sukses.
- [ ] Masing-masing error Telegram dipetakan ke kode stabil.
- [ ] `FloodWait` tidak menggagalkan proses; `retry_after` dikembalikan.
- [ ] Logout menghapus berkas sesi & memperbarui status.
- [ ] Tidak ada api_hash/kode/password di log (tes).
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q10 (lokasi/penamaan sesi), Q11 (dukungan 2FA wajib).
