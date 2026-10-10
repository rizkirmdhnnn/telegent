# C2 — UI settings

- **Epic/Fase:** C / Fase 1
- **Dependensi:** C1, B1, B3
- **Estimasi:** L
- **Referensi:** spec §4, §8.3 · open-questions Q8/Q9

## Konteks
Form konfigurasi lengkap bergrup dengan validasi klien, badge penerapan, dan alur
"Terapkan & Restart".

## Tujuan
- Halaman `/settings` dengan seksi per grup (kredensial, akun Telegram, model, persona,
  kebijakan akses, anti-idle, logging, aplikasi, advanced).
- Render tipe field yang tepat (text, textarea, number, boolean, list/chip, select).
- Validasi klien + pesan error server ter-i18n.
- Indikator `hot`/`restart` dan tombol apply bila ada perubahan `restart` tertunda.

## Deliverable
- `frontend/src/routes/(app)/settings/+page.svelte`
- Komponen `SettingField` (dispatch berdasarkan tipe), `SettingsSection`,
  `RestartPendingBar`

## Langkah implementasi
1. Ambil `/api/settings` + `/api/settings/schema`; bangun form per grup.
2. `SettingField`: tipe → kontrol shadcn (Input/Textarea/Switch/Select/Badge list).
3. Simpan: kirim hanya field berubah via `PUT /settings`; tampilkan toast hasil.
4. Bila `needs_restart` non-kosong: tampilkan bar + tombol **Terapkan & Restart**
   (memanggil `/api/runtime/apply` atau `/restart` — F2).
5. Seksi **Advanced**: field audio (read-only) disembunyikan default (Q9).
6. Reset ke default (per field) bila didukung.

## Kriteria terima (Definition of Done)
- [ ] Semua setting pada spec §4 dapat diubah (kecuali bootstrap/advanced read-only).
- [ ] Field invalid ditandai sebelum submit + pesan error server ditampilkan.
- [ ] Perubahan hot langsung tercermin (tanpa restart); badge `restart` benar.
- [ ] Tombol apply memicu restart & hilangkan badge saat selesai.
- [ ] `allowed_user_ids` di-render sebagai chip multiline (Q8).
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Q8 (chip list), Q9 (advanced read-only).
