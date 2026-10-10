# B1 — Scaffold SvelteKit + shadcn-svelte + i18n + API client

- **Epic/Fase:** B / Fase 1
- **Dependensi:** A1
- **Estimasi:** L
- **Referensi:** plan §5 (ADR-2) · spec §10 · open-questions Q6/Q7

## Konteks
Butuh fondasi SPA: routing, komponen UI, tema, i18n, dan klien API yang menghormati
cookie sesi + CSRF.

## Tujuan
- Proyek SvelteKit (adapter-static, SPA mode) di `frontend/`.
- shadcn-svelte + Tailwind terpasang & terdokumentasi.
- Klien API terpusat (base `/api`, kredensial cookie, auto CSRF, penanganan error kode).
- i18n (id default + en) + tema terang/gelap.

## Deliverable
- `frontend/` (SvelteKit, Tailwind, shadcn-svelte)
- `frontend/src/lib/api.ts` (fetch wrapper)
- `frontend/src/lib/i18n/` (katalog `id.json`, `en.json`, helper `t()`)
- `frontend/src/lib/stores/` (locale, theme, session)

## Langkah implementasi
1. Inisialisasi SvelteKit + Tailwind + shadcn-svelte (Q7: Svelte 5).
2. Konfigurasi `adapter-static` dengan fallback SPA (agar routing klien bekerja).
3. Buat API client: base URL `/api`, `credentials: "include"`, sisipkan `X-CSRF-Token`
   dari cookie, parse `{error:{code,message,fields}}` → error ter-i18n.
4. Setup i18n ringan (katalog + `t(key)` + deteksi/pilihan locale).
5. Setup tema (class `dark` pada `<html>` + penyimpanan preferensi).
6. Skrip build → output ke lokasi yang dilayani FastAPI (A1).

## Kriteria terima (Definition of Done)
- [ ] `npm run build` menghasilkan bundel statis yang dilayani FastAPI di `/`.
- [ ] Routing klien (deep-link) bekerja via fallback SPA.
- [ ] Memanggil `/api/healthz` dari SPA berhasil.
- [ ] Ganti bahasa id↔en mengubah teks; pilihan tersimpan.
- [ ] Ganti tema terang/gelap berfungsi.
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Q6 (SvelteKit static), Q7 (Svelte 5 + shadcn-svelte).
