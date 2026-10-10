# F2 — UI kontrol runtime + indikator "butuh restart" + alur apply

- **Epic/Fase:** F / Fase 4
- **Dependensi:** F1, C2, B3
- **Estimasi:** M
- **Referensi:** spec §6.2, §6.5, §8.3

## Konteks
Perlu antarmuka jelas untuk mengendalikan proses dan menerapkan perubahan yang
memerlukan restart, dengan umpan balik status.

## Tujuan
- Kontrol start/stop/restart di dashboard & pengaturan (dengan konfirmasi).
- Bar "perubahan butuh restart" + tombol **Terapkan & Restart**.
- Umpan balik proses (transition state) & tampilan error.

## Deliverable
- Komponen `RuntimeControl`, `RestartPendingBar`, `ConfirmDialog`
- Integrasi ke dashboard (B3/E3) & settings (C2)

## Langkah implementasi
1. `RuntimeControl`: tombol dinamis berdasarkan status (start bila stopped; stop bila
   running; restart bila running), dengan dialog konfirmasi (sebutkan sesi aktif).
2. `RestartPendingBar` muncul di layout saat `pending_restart` (dari status settings
   atau store lokal) → tombol memanggil `/runtime/apply`.
3. Tampilkan transisi (starting/stopping) & error (`last_error`) ter-i18n.
4. Setelah restart/apply sukses → refresh status & bersihkan badge.

## Kriteria terima (Definition of Done)
- [ ] Tombol kontrol sesuai status & mencegah aksi ganda saat transisi.
- [ ] Konfirmasi menampilkan dampak (mis. "2 panggilan aktif akan diakhiri").
- [ ] Apply menghilangkan badge & memperbarui status.
- [ ] Error runtime tampil jelas dengan tindakan lanjut.
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Kebijakan drain vs force saat restart dengan sesi aktif — tampilkan pilihan bila perlu.
