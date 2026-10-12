# A3 — Crypto secret (kunci file + Fernet)

- **Epic/Fase:** A / Fase 0
- **Dependensi:** A1
- **Estimasi:** S
- **Referensi:** plan §5 (ADR-6) · spec §9

## Konteks
API key Gemini dan `telegram_api_hash` harus disimpan terenkripsi at-rest. Kunci
tidak boleh menuntut langkah CLI (selaras tujuan "full website").

## Tujuan
- Kunci Fernet auto-generate ke `data/.secret_key` (chmod 600) bila belum ada.
- Override via `TELEGENT_SECRET_KEY`.
- API enkripsi/dekripsi sederhana + masking untuk UI/audit.

## Deliverable
- `src/telegent/web/crypto.py` (`SecretCipher`)
- Fungsi `load_or_create_key(path)`, `encrypt(str)->str`, `decrypt(str)->str`,
  `mask(str)->str`

## Langkah implementasi
1. Tambah dependensi `cryptography`.
2. `load_or_create_key`: baca env; jika kosong baca file; jika tidak ada → generate,
   tulis dengan izin `0600` (buat direktori bila perlu).
3. `SecretCipher` membungkus `Fernet`.
4. `mask`: tampilkan sebagian (mis. `AIza****abcd`) dan selalu non-reversible.

## Kriteria terima (Definition of Done)
- [ ] File kunci dibuat sekali, izin `0600`, dipakai ulang pada boot berikutnya.
- [ ] Round-trip encrypt→decrypt konsisten (tes).
- [ ] `mask` tidak pernah membocorkan nilai penuh.
- [ ] Bila `TELEGENT_SECRET_KEY` diisi, file tidak dibuat.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Tidak ada (default dari open-questions diterima).
