# D2 — API akun & login Telegram

- **Epic/Fase:** D / Fase 2
- **Dependensi:** D1, A5
- **Estimasi:** M
- **Referensi:** spec §6.4

## Konteks
Layanan login (D1) perlu dibungkus endpoint REST yang aman & ter-audit.

## Tujuan
- `GET /telegram/status`
- `POST /telegram/login/start`, `/verify`, `/password`, `/cancel`
- `POST /telegram/logout`
- Semua mutasi tercatat di audit; error memakai kode stabil.

## Deliverable
- `src/telegent/web/routers/telegram.py`
- Skema request/response

## Langkah implementasi
1. Bungkus `TelegramLoginService` (D1) sebagai endpoint.
2. Validasi prasyarat: kredensial Telegram harus ada → jika tidak, kembalikan
   `api_credentials_missing`.
3. `status`: dari `telegram_account` + state runtime.
4. Terjemahkan pengecualian D1 → respons JSON kode stabil (`code`, opsional `retry_after`).
5. `logout` → clear sesi + status; picu audit.

## Kriteria terima (Definition of Done)
- [ ] Seluruh alur login dapat dijalankan via HTTP tanpa terminal.
- [ ] Tanpa kredensial → error jelas (bukan 500).
- [ ] `FloodWait` → `{code:"flood_wait", retry_after:N}`.
- [ ] Setiap login/logout menghasilkan entri audit.
- [ ] Tes: alur sukses & error (fake).
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Koordinasi dengan runtime: setelah login, admin diminta start/restart (F1/F2).
