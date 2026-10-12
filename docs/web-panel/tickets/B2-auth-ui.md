# B2 — UI auth: setup wizard, login, akun/TOTP

- **Epic/Fase:** B / Fase 1
- **Dependensi:** A5, B1
- **Estimasi:** M
- **Referensi:** spec §6.1, §8.1, §8.2

## Konteks
Pengguna perlu membuat admin pertama, login, dan mengelola profil (bahasa/tema/2FA).

## Tujuan
- Halaman `/setup` (wizard) bila belum ada admin.
- Halaman `/login` (password + TOTP bila aktif).
- Halaman `/account` (ganti password, aktif/nonaktif TOTP, locale/tema).

## Deliverable
- `frontend/src/routes/setup/+page.svelte`
- `frontend/src/routes/login/+page.svelte`
- `frontend/src/routes/account/+page.svelte`
- Guard route (redirect ke login bila belum terautentikasi)

## Langkah implementasi
1. Cek `/api/setup/status` saat boot → arahkan ke `/setup` atau `/login`.
2. Wizard setup: buat admin → otomatis lanjut ke wizard kredensial (C4) & Telegram (D3).
3. Login: form password; bila respons menuntut TOTP → tampilkan field kode.
4. Tampilkan pesan error berbasis `code` i18n; hitung mundur pada lockout.
5. Halaman akun: form ganti password; setup TOTP (QR SVG) + verifikasi kode; toggle tema/bahasa.

## Kriteria terima (Definition of Done)
- [ ] Alur setup → login → dashboard mulus tanpa reload penuh.
- [ ] Deep-link ke halaman terproteksi tanpa sesi → diarahkan ke `/login`.
- [ ] TOTP: enable dengan kode valid, login berikutnya menuntut kode.
- [ ] Error login (salah/lockout) tampil ter-i18n.
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Reuse komponen form shadcn (Input, Button, Card, Dialog).
