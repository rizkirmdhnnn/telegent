# A2 — Lapisan DB SQLAlchemy async + model + Alembic

- **Epic/Fase:** A / Fase 0
- **Dependensi:** A1
- **Estimasi:** L
- **Referensi:** plan §5 (ADR-4), §6 · spec §5

## Konteks
Konfigurasi, observability, dan audit memerlukan penyimpanan persisten. Gunakan
SQLite dengan SQLAlchemy async dan Alembic untuk migrasi.

## Tujuan
- Engine async (`sqlite+aiosqlite`) dengan WAL + `busy_timeout`.
- Seluruh model dari spec §5 terdefinisi.
- Alembic siap (`alembic upgrade head`) dan dijalankan saat boot.

## Deliverable
- `src/telegent/web/db/base.py` (engine, `async_sessionmaker`, PRAGMA)
- `src/telegent/web/db/models.py` (AdminUser, AppSetting, TelegramAccount, LoginFlow,
  CallRecord, TranscriptEntry, ToolCallRecord, ToolConfig, AuditLog)
- `src/telegent/web/db/migrations/` (Alembic env + revisi awal)
- `alembic.ini` atau konfigurasi programatik

## Langkah implementasi
1. Tambah dependensi: `sqlalchemy[asyncio]`, `aiosqlite`, `alembic`.
2. Definisikan `Base` (Declarative) + engine dari `TELEGENT_DB_URL`.
3. Aktifkan `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout`.
4. Implementasi seluruh model + relasi (cascade untuk transkrip/tool call).
5. Inisialisasi Alembic; buat revisi awal dari model.
6. Jalankan `upgrade head` pada startup aplikasi (idempoten).

## Kriteria terima (Definition of Done)
- [ ] DB terbentuk otomatis di `data/telegent.db` saat boot pertama.
- [ ] `alembic upgrade head` idempoten (tidak error bila sudah terbaru).
- [ ] WAL aktif (verifikasi `PRAGMA journal_mode`).
- [ ] Model menutupi seluruh tabel spec §5.
- [ ] Tes: buat/tutup sesi, insert+query satu record tiap tabel.
- [ ] `pyright` hijau.

## Catatan teknis / pertanyaan
- Q1: konfirmasi WAL + satu engine bersama bot & web.
