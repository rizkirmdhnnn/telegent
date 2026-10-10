# B3 — App shell: navigasi, layout, tema, bahasa

- **Epic/Fase:** B / Fase 1
- **Dependensi:** B1
- **Estimasi:** M
- **Referensi:** plan §7

## Konteks
Butuh kerangka navigasi konsisten untuk semua halaman (dashboard, panggilan, setting,
telegram, tool, log, audit, akun) dengan kontrol tema & bahasa.

## Tujuan
- Layout aplikasi: sidebar/topbar, area konten, indikator status runtime (dari SSE).
- Menu: Dashboard, Panggilan, Konfigurasi, Kredensial, Telegram, Tool, Log, Audit, Akun.
- Kontrol tema + bahasa di topbar; indikator koneksi live.

## Deliverable
- `frontend/src/routes/(app)/+layout.svelte`
- Komponen nav, `StatusBadge`, `LanguageSwitch`, `ThemeSwitch`
- Store status runtime yang berlangganan `/api/events/stream`

## Langkah implementasi
1. Layout terproteksi untuk grup `(app)`.
2. Sidebar responsif + highlight route aktif; judul halaman dari i18n.
3. Komponen `StatusBadge` menampilkan state runtime (active/stopped/needs_login/error)
   dari aliran SSE (fallback poll bila SSE gagal).
4. Kontrol bahasa & tema; sinkron ke `/api/auth/me` (PATCH).

## Kriteria terima (Definition of Done)
- [ ] Navigasi antar halaman tanpa reload penuh.
- [ ] Status runtime berubah di UI saat bus menerbitkan event (uji dengan toggle).
- [ ] Tema & bahasa persist antar reload.
- [ ] Aksesibel (focus, aria dasar) & responsif.
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Indikator status bergantung pada A8/E3; sementara boleh polling `/api/runtime/status`.
