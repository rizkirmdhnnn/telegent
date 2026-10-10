# A6 — Audit log

- **Epic/Fase:** A / Fase 0
- **Dependensi:** A2, A4
- **Estimasi:** S
- **Referensi:** spec §5.9, §9

## Konteks
Perubahan konfigurasi & aksi administratif harus dapat diaudit (siapa, kapan, apa).

## Tujuan
- Helper tunggal `record_audit(actor, action, target, before, after, ip)`.
- Nilai secret **selalu** dimask sebelum ditulis.
- Endpoint `GET /audit` (paginasi) untuk konsumsi UI.

## Deliverable
- `src/telegent/web/audit.py`
- `src/telegent/web/routers/audit.py`

## Langkah implementasi
1. Implementasi `record_audit` menulis ke `audit_log` (A2).
2. Reuse `crypto.mask` (A3) untuk field sensitif; util `sanitize_diff`.
3. Panggil dari: settings update (A4), credential update (C3), runtime restart (F1),
   telegram login/logout (D2), auth events (A5).
4. `GET /audit` dengan `page`, `page_size`, filter `action`.

## Kriteria terima (Definition of Done)
- [ ] Setiap perubahan setting/kredensial menghasilkan entri audit.
- [ ] Tidak ada nilai secret penuh di `before/after`.
- [ ] Audit tidak ikut terhapus oleh retensi transkrip.
- [ ] Tes: masking diff + paginasi.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Pastikan actor & ip tersedia dari dependency `current_admin`.
