# C3 — API kredensial + validasi, dan API tool

- **Epic/Fase:** C / Fase 1
- **Dependensi:** A3, A4, A5
- **Estimasi:** M
- **Referensi:** spec §6.3, §6.7

## Konteks
Kredensial Telegram/Gemini perlu disimpan (terenkripsi) dan divalidasi; tool bawaan
perlu bisa di-toggle & dikonfigurasi.

## Tujuan
- `PUT /credentials/telegram`, `PUT /credentials/gemini`, `POST /credentials/validate`.
- `GET /tools`, `PUT /tools/{name}`.
- Perubahan kredensial menandai runtime perlu restart (`needs_restart`).

## Deliverable
- `src/telegent/web/routers/credentials.py`
- `src/telegent/web/routers/tools.py`
- Modifikasi `ToolRegistry` agar menerima konfigurasi/enable dari store (tanpa
  mengubah perilaku default).

## Langkah implementasi
1. Simpan kredensial via `SettingsStore` (secret → terenkripsi); tandai `restart`;
   tulis audit (mask).
2. `validate`:
   - telegram: cek format `api_id`/`api_hash` + koneksi ringan bila sesi tersedia.
   - gemini: cek format + ping model ringan bila memungkinkan.
3. Tools: daftar dari registry + `tool_config`; `PUT` menyimpan `enabled`/`config`.
4. Integrasi: `default_tools()` (atau registry) membaca `tool_config` dari store saat
   runtime dibangun / hot-apply.

## Kriteria terima (Definition of Done)
- [ ] Kredensial tersimpan terenkripsi; respons tidak mengembalikan nilai penuh.
- [ ] `validate` mengembalikan `{valid, message}` yang jelas & ter-i18n (kode).
- [ ] Mengubah kredensial menandai `needs_restart`.
- [ ] `get_current_datetime` dapat diubah zona waktu default-nya lewat `config`.
- [ ] Menonaktifkan tool menghilangkan deklarasinya ke Gemini pada panggilan baru.
- [ ] `end_call` tidak dapat dinonaktifkan (selalu aktif) — atau kebijakan eksplisit.
- [ ] Tes: simpan+mask, validate (fake), toggle tool.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Pastikan `end_call` selalu tersedia (kebijakan) atau didokumentasikan bila bisa off.
