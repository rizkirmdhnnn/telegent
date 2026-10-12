# C1 — API settings + endpoint schema

- **Epic/Fase:** C / Fase 1
- **Dependensi:** A4, A5
- **Estimasi:** M
- **Referensi:** spec §6.2, §4, §8.3

## Konteks
UI memerlukan daftar setting (bergrup, ter-mask) dan metadata untuk membangun form
yang tepat (tipe, validasi, label, hot/restart).

## Tujuan
- `GET /settings` (nilai bergrup, secret ter-mask, `pending_restart`).
- `GET /settings/schema` (metadata registry).
- `PUT /settings` (batch partial update) → `{applied, needs_restart}`.

## Deliverable
- `src/telegent/web/routers/settings.py`
- Skema pydantic request/response

## Langkah implementasi
1. `GET /settings`: gabungkan nilai store + spec; mask secret; sertakan tipe/grup.
2. `GET /settings/schema`: ekspos registry (label i18n key, tipe, validasi, group,
   penerapan, secret flag).
3. `PUT /settings`: validasi via `SettingsStore.update`; tulis audit (A6); bila ada
   perubahan `hot`, picu `RuntimeController.set_settings` (A7); tandai `needs_restart`.
4. `pending_restart`: bandingkan nilai tersimpan vs nilai runtime terakhir dipakai.

## Kriteria terima (Definition of Done)
- [ ] `GET /settings` tidak pernah memuat secret penuh.
- [ ] `PUT` dengan nilai invalid → 422 + error per-field.
- [ ] `PUT` hot → respons `applied` memuat key tersebut dan runtime terbarui.
- [ ] `PUT` restart → key muncul di `needs_restart`, runtime tidak berubah sampai apply.
- [ ] Audit tercatat untuk setiap key yang berubah.
- [ ] Tes API end-to-end (dengan DB & fake runtime).
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q8/Q9 (format & tampilan field tertentu).
