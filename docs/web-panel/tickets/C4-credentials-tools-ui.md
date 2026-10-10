# C4 — UI kredensial + tool

- **Epic/Fase:** C / Fase 1
- **Dependensi:** C3, B3
- **Estimasi:** M
- **Referensi:** spec §6.3, §6.7

## Konteks
Admin perlu mengisi/memperbarui kredensial dengan jelas dan memvalidasinya, serta
mengelola tool bawaan.

## Tujuan
- Halaman `/credentials`: form Telegram (api_id/api_hash) & Gemini (API key) dengan
  tombol validasi & indikator status.
- Halaman `/tools`: daftar tool, toggle enable, editor `config`.

## Deliverable
- `frontend/src/routes/(app)/credentials/+page.svelte`
- `frontend/src/routes/(app)/tools/+page.svelte`

## Langkah implementasi
1. Credentials: field masked untuk secret; tampilkan bahwa nilai lama tetap ada bila
   tidak diubah; tombol "Validasi" memanggil `/credentials/validate`.
2. Tampilkan status kredensial (terisi/belum) + badge `needs_restart`.
3. Tools: kartu per tool dengan deskripsi, switch enable, dan form config (mis. zona
   waktu default). Simpan via `PUT /tools/{name}`.
4. Petunjuk inline: link ke halaman Telegram untuk login setelah kredensial terisi.

## Kriteria terima (Definition of Done)
- [ ] Tidak ada secret penuh yang pernah dirender; placeholder masking jelas.
- [ ] Validasi menampilkan hasil sukses/gagal yang dapat ditindaklanjuti.
- [ ] Tool toggle tersimpan & tercermin di UI setelah reload.
- [ ] `svelte-check` hijau.

## Catatan teknis / pertanyaan
- Jika kredensial belum valid, arahkan ke login Telegram (D3) dengan jelas.
