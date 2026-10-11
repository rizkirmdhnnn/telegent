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
- `src/telegent/web/retention_store.py` (pola `*_store.py`, bukan `retention.py`)
- Penjadwalan di `lifespan` (harian + saat boot)

## Langkah implementasi
1. Fungsi `cleanup(session)` menghapus data lampau ambang berdasarkan setting.
2. Jadwalkan harian (Q15) + jalankan sekali saat boot.
3. Jalankan dalam batch kecil; log ringkas (jumlah terhapus), tanpa data isi.

## Kriteria terima (Definition of Done)
- [x] Data melebihi retensi terhapus; data dalam rentang tetap.
- [x] `0` berarti tanpa batas (tidak menghapus).
- [x] `audit_log` tidak pernah terhapus.
- [x] Tes dengan data bertanggal buatan.
- [x] `pyright` hijau.

## Catatan teknis / pertanyaan
- **Q15 (jadwal):** satu siklus saat boot (`lifespan`), lalu task yang mengulang
  tiap 24 jam. Kegagalan satu siklus dicatat dan tidak menghentikan penjadwalan.
- **`transcript_entry`:** karena `call_record` dihapus dengan cascade, transkrip
  yang masih punya induk ikut terhapus. Sisa "yatim" (induk hilang di luar
  aplikasi) ditangani `delete_orphan_transcripts`.
