# A5 — Auth admin + first-run setup + TOTP

- **Epic/Fase:** A / Fase 0
- **Dependensi:** A2, A3
- **Estimasi:** L
- **Referensi:** spec §6.1, §9 · open-questions Q2/Q3

## Konteks
Panel mengendalikan akun Telegram & API key, jadi butuh autentikasi. Single-tenant →
satu akun admin saja, dibuat lewat wizard pertama kali.

## Tujuan
- Model & CRUD admin tunggal (lihat spec §5.1).
- Password di-hash (argon2, fallback bcrypt).
- Sesi berbasis cookie (server-side) + token CSRF.
- First-run setup (`/setup/status`, `/setup/admin`).
- TOTP opsional (setup/enable/disable).
- Rate-limit login + lockout.

## Deliverable
- `src/telegent/web/security.py` (hashing, session store, CSRF, TOTP)
- `src/telegent/web/routers/auth.py`
- `src/telegent/web/routers/setup.py`
- `src/telegent/web/deps.py` (`current_admin` dependency)

## Langkah implementasi
1. Tambah dependensi: `argon2-cffi` (atau `passlib[bcrypt]`), `pyotp`; sesi via
   `itsdangerous`/tabel sesi.
2. Setup: bila `admin_user` kosong → `needs_setup=true`; `POST /setup/admin` membuat
   admin + auto-login. Tolak bila admin sudah ada.
3. Login: verifikasi hash (+TOTP), set cookie sesi (`httpOnly`, `SameSite=Lax`) dan
   cookie CSRF. Catat `failed_attempts`, lockout sesuai Q3.
4. Dependency `current_admin` memvalidasi sesi + CSRF (untuk mutasi).
5. TOTP: `setup` (secret+QR SVG), `enable(code)`, `disable(code)`; simpan secret
   terenkripsi (A3).
6. `PATCH /auth/me` (locale/theme), `POST /auth/password`.
7. Header keamanan dasar (nosniff, frame-deny, referrer).

## Kriteria terima (Definition of Done)
- [ ] `/setup/status` benar sebelum & sesudah admin dibuat.
- [ ] Login sukses men-set cookie; logout menghapusnya.
- [ ] Mutasi tanpa CSRF ditolak 403.
- [ ] Lockout aktif setelah N percobaan gagal (Q3) dan pulih setelah durasi.
- [ ] TOTP enable→login-menuntut-kode→verify→disable bekerja.
- [ ] Password tersimpan hanya sebagai hash.
- [ ] Tes: setup, login, lockout, CSRF, TOTP.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q2 (argon2 vs bcrypt), Q3 (ambang lockout).
