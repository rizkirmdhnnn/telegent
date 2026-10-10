# A4 — Settings registry + SettingsStore

- **Epic/Fase:** A / Fase 0
- **Dependensi:** A2, A3
- **Estimasi:** L
- **Referensi:** plan §5 (ADR-5) · spec §4

## Konteks
`.env` saat ini menjadi satu-satunya sumber `Settings`. Kita pindah ke DB sebagai
sumber kebenaran, dengan registry metadata yang menjadi acuan validasi & UI.

## Tujuan
- `settings_registry.py`: metadata lengkap semua setting (label i18n, tipe, grup,
  default, validasi, penerapan hot/restart/bootstrap, sensitif).
- `SettingsStore`: bangun objek `telegent.config.Settings` dari DB (fallback env saat
  bootstrap), simpan perubahan, dan query daftar untuk UI (dengan masking).
- Import `.env` lama on-first-run.

## Deliverable
- `src/telegent/web/settings_registry.py`
- `src/telegent/web/settings_store.py`
- Penyesuaian kecil `telegent.config.Settings` bila perlu (mis. konstruktor dari dict).

## Langkah implementasi
1. Definisikan struktur metadata (`SettingSpec`) + list lengkap per spec §4.
2. `get_all(mask_secrets=True)`, `get(key)`, `get_typed(key)`.
3. `update(changes, actor)` → validasi tiap key (tipe + aturan) → simpan (enkripsi bila
   secret) → kembalikan `{applied:[hot], needs_restart:[restart]}` → picu audit (A6).
4. `build_settings() -> Settings`: gabungkan nilai DB + fallback env + default;
   lempar `NotConfigured` bila kredensial wajib belum ada.
5. `import_from_env_once()`: bila tabel kosong dan `.env` ada, salin nilai yang cocok.
6. Redaksi: pastikan nilai secret tidak pernah keluar mentah dari store.

## Kriteria terima (Definition of Done)
- [ ] `GET` daftar setting mem-mask secret (mask tidak reversible).
- [ ] `build_settings()` menghasilkan `Settings` valid bila kredensial lengkap; melempar
  `NotConfigured` bila belum.
- [ ] Import `.env` lama berjalan sekali dan tidak menimpa nilai DB (Q20).
- [ ] `update` menolak nilai invalid dengan error per-field.
- [ ] Tes: validasi, hot vs restart classification, masking.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q8 (format `allowed_user_ids`), Q9 (field audio lanjutan), Q20 (env vs DB).
