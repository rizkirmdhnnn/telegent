# H3 — E2E Playwright + perluasan CI

- **Epic/Fase:** H / Fase 5
- **Dependensi:** H1, H2, G1
- **Estimasi:** L
- **Referensi:** plan §8, §11 · open-questions Q17

## Konteks
Perlu verifikasi alur end-to-end (login → setup → ubah config → lihat status) dan CI
yang menjalankan seluruh gerbang kualitas.

## Tujuan
- Skenario e2e Playwright untuk alur utama, memakai **mode fake** (tanpa Telegram/Gemini).
- CI diperluas: backend (pytest + pyright) + frontend (svelte-check + unit + build) + e2e.

## Deliverable
- `frontend/e2e/` (Playwright) + konfigurasi
- `.github/workflows/ci.yml` (diperbarui)
- Helper menjalankan backend fake (feature flag / env `TELEGENT_FAKE=1`)

## Langkah implementasi
1. Tambah mode fake: startup tanpa kredensial nyata, runtime fake yang menerbitkan
   event buatan (status, panggilan, transkrip, log) untuk memverifikasi UI live.
2. Skenario: setup admin → login → isi kredensial (fake valid) → "login telegram"
   (fake) → ubah setting hot & restart → start bot → verifikasi dashboard/log live →
   lihat riwayat/transkrip.
3. Playwright: jalankan server (uvicorn) + webServer config; tunggu healthz.
4. CI: matrix/urutan langkah; cache Node & uv; unggah artefak laporan Playwright saat gagal.

## Kriteria terima (Definition of Done)
- [ ] Semua skenario e2e lulus di CI tanpa kredensial/jaringan Telegram/Gemini.
- [ ] `ci.yml` menjalankan pytest, pyright, svelte-check, unit, build, dan e2e.
- [ ] CI hijau pada PR contoh (dry-run).
- [ ] Laporan Playwright diunggah saat gagal.
- [ ] Dokumentasi menjalankan e2e lokal ditambahkan.

## Catatan teknis / pertanyaan
- Q17 (fake untuk determinisme). Pastikan flag fake tidak bisa aktif di produksi secara
  tidak sengaja (butuh env eksplisit + peringatan).
