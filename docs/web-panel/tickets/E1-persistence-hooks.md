# E1 — Hook persistensi: call record, transkrip, tool call

- **Epic/Fase:** E / Fase 3
- **Dependensi:** A2, A7, A8
- **Estimasi:** L
- **Referensi:** spec §5.5–5.7, §8.5 · open-questions Q12/Q13

## Konteks
`CallSession` sudah menghasilkan event transkrip & tool call. Kita perlu menyimpannya
ke DB dan menerbitkannya ke EventBus, tanpa mengubah perilaku audio.

## Tujuan
- `call_record` dibuat saat panggilan **masuk** (termasuk penolakan) dan diakhiri saat
  panggilan selesai.
- `transcript_entry` & `tool_call_record` ditulis saat event terkait (opsional bila
  `store_transcripts=false`).
- Event diterbitkan ke bus untuk UI live.

## Deliverable
- `src/telegent/web/persistence.py` (repo fungsi insert/update)
- Hook di `TelegentApp` (saat menerima/menolak/mengakhiri) dan opsional di `CallSession`
  (transkrip/tool) via callback yang tidak mengganggu pipeline.

## Langkah implementasi
1. Tambah callback opsional ke `CallSession` (mis. `on_event`) yang dipanggil untuk
   TranscriptIn/Out & ToolCall; default `None` agar tes lama tetap lulus.
2. Di `TelegentApp`: buat/akhiri `call_record` untuk tiap outcome (whitelist, rate-limit,
   kapasitas, duplikat, answered, error) dengan `end_reason` yang tepat.
3. Tulis transkrip/tool call ke DB (hormati `store_transcripts`); publish ke bus (A8).
4. Hindari blocking loop: gunakan sesi DB async & batch kecil; jangan menahan audio.
5. Pastikan durasi & `tool_call_count`/`transcript_count` ter-update saat berakhir.

## Kriteria terima (Definition of Done)
- [ ] Setiap panggilan (diterima/ditolak) menghasilkan satu `call_record`.
- [ ] Transkrip & tool call tersimpan (bila diaktifkan) dan terhubung ke record.
- [ ] Event live terkirim ke bus (diverifikasi via subscriber tes).
- [ ] Pipeline audio tidak berubah; tes lama tetap hijau.
- [ ] `store_transcripts=false` benar-benar menghentikan penyimpanan teks.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q12 (kapan record dibuat), Q13 (default simpan transkrip).
