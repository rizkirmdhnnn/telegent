# H1 — Test backend (API, auth, crypto, settings, runtime)

- **Epic/Fase:** H / Fase 5
- **Dependensi:** A–F (berkembang sepanjang fase)
- **Estimasi:** L
- **Referensi:** plan §8, §11 · open-questions Q17

## Konteks
Fitur web menyentuh auth, secret, dan data; perlu cakupan tes kuat dengan fake agar
deterministik (tanpa Telegram/Gemini nyata).

## Tujuan
- Tes unit & integrasi untuk: crypto, settings store, auth/setup/CSRF/TOTP, audit
  masking, kredensial, tool toggle, telegram login (fake), persistence, monitoring API,
  runtime control (fake runtime).
- TestClient FastAPI + DB SQLite sementara (in-memory/temp file).

## Deliverable
- `tests/web/` (modul per domain)
- Helper/fixture: DB sementara, admin login, fake runtime, fake telegram.

## Langkah implementasi
1. Fixture `app_client` (create_app + DB temp) & `auth_client` (login admin).
2. Uji skenario kritis: tanpa CSRF ditolak; secret tidak bocor (endpoint & audit);
   import `.env` sekali; hot vs restart; error telegram terpetakan.
3. Uji redaksi log handler (A8).
4. Uji retensi (F3) dengan data bertanggal.
5. Pastikan tes lama (audio/tools/rate-limit) tetap hijau.

## Kriteria terima (Definition of Done)
- [x] `uv run pytest -q` hijau, termasuk tes web baru.
- [x] Cakupan skenario kritis (auth, secret, setting, telegram, monitoring) ada.
- [x] Fake runtime/telegram memisahkan tes dari jaringan.
- [x] `uv run pyright src/telegent` hijau.
- [x] Tes lama tidak berubah perilaku.

## Catatan teknis / pertanyaan
- Q17 (fake untuk determinisme).
