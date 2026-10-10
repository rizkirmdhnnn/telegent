# D3 — UI login/akun Telegram

- **Epic/Fase:** D / Fase 2
- **Dependensi:** D2, B3
- **Estimasi:** M
- **Referensi:** spec §6.4, §8.4

## Konteks
Admin perlu pengalaman login Telegram yang jelas: input nomor → kode → password 2FA,
serta melihat status akun dan melakukan logout.

## Tujuan
- Halaman `/telegram`: status akun, alur login bertahap, logout.
- Penanganan 2FA, error kode kedaluwarsa, dan hitung mundur FloodWait.
- Tombol lanjut: start/restart runtime setelah login.

## Deliverable
- `frontend/src/routes/(app)/telegram/+page.svelte`
- Komponen `TelegramLoginStepper`

## Langkah implementasi
1. READ status → jika `logged_in`, tampilkan profil akun (nama/@username/id) + logout.
2. Stepper: (1) nomor telepon → (2) kode → (3) password (kondisional) → (4) sukses.
3. Simpan `flow_id` di state; kirim ke endpoint verify/password.
4. Tampilkan error ter-i18n; hitung mundur bila `flood_wait`.
5. Setelah sukses: tawarkan "Jalankan bot sekarang" (F1) / "Terapkan & Restart" (F2).

## Kriteria terima (Definition of Done)
- [ ] Alur login selesai tanpa reload penuh & tanpa terminal.
- [ ] Langkah password hanya muncul saat diperlukan.
- [ ] Error kode invalid/expired & flood-wait tampil dengan jelas.
- [ ] Setelah login, status akun & tombol jalankan bot tampil.
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Q11 (2FA didukung penuh).
