# H2 — Test frontend (unit + svelte-check)

- **Epic/Fase:** H / Fase 5
- **Dependensi:** B–F
- **Estimasi:** M
- **Referensi:** plan §8, §11

## Konteks
SPA perlu jaminan tipe & unit test untuk logika non-UI (api client, i18n, store).

## Tujuan
- `svelte-check` tanpa error.
- Unit test untuk API client (CSRF, error mapping), i18n, dan store (status/locale/theme).
- Build produksi sukses (gate CI).

## Deliverable
- `frontend/` konfigurasi test (Vitest) + tes `src/lib/**/*.test.ts`
- Skrip `check`, `test`, `build` di `package.json`

## Langkah implementasi
1. Pasang Vitest (+ jsdom bila perlu untuk komponen ringan).
2. Tes api client: menyisipkan CSRF, memetakan `{error:{code}}` ke pesan i18n.
3. Tes i18n: kunci ada di kedua katalog (id/en) — deteksi kunci hilang.
4. Tes store: set locale/theme & persist.
5. Pastikan `npm run build` bersih untuk produksi.

## Kriteria terima (Definition of Done)
- [x] `svelte-check` hijau.
- [x] `npm run test` hijau.
- [x] `npm run build` sukses.
- [x] Uji "kunci i18n hilang" mencegah regresi terjemahan.
- [x] Integrasi ke CI (H3).

## Catatan teknis / pertanyaan
- Fokus logika; hindari tes UI kaku (ditutup e2e H3).
