# F3 — Pembersihan retensi

- **Epic/Fase:** F / Fase 4
- **Dependensi:** A2, E1
- **Estimasi:** S
- **Referensi:** spec §4, §5 · open-questions Q15

## Konteks
Riwayat & transkrip dapat tumbuh tak terbatas. Butuh pembersihan terjadwal sesuai
kebijakan retensi.

## Tujuan
- Tugas terjadwal yang menghapus `call_record` (beserta transkrip/tool call-nya via
  cascade) dan `transcript_entry` yang lebih tua dari retensi.
- Menghormati `calls_retention_days` & `transcripts_retention_days` (0 = selamanya).
- `store_transcripts=false` → tidak menyimpan (dari E1); retensi tetap membersihkan sisa lama.
- Tidak menyentuh `audit_log`.

## Deliverable
- `src/telegent/web/retention.py`
- Penjadwalan di `lifespan` (harian + saat boot)

## Langkah implementasi
1. Fungsi `cleanup(session)` menghapus data lampau ambang berdasarkan setting.
2. Jadwalkan harian (Q15) + jalankan sekali saat boot.
3. Jalankan dalam batch kecil; log ringkas (jumlah terhapus), tanpa data isi.

## Kriteria terima (Definition of Done)
- [ ] Data melebihi retensi terhapus; data dalam rentang tetap.
- [ ] `0` berarti tanpa batas (tidak menghapus).
- [ ] `audit_log` tidak pernah terhapus.
- [ ] Tes dengan data bertanggal buatan.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q15 (jadwal harian).
