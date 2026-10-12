# A1 — Skeleton web FastAPI + mount SPA + healthz

- **Epic/Fase:** A / Fase 0
- **Dependensi:** —
- **Estimasi:** M
- **Referensi:** plan §5 (ADR-1), §6 · spec §2

## Konteks
Belum ada aplikasi web. Tiket ini membuat kerangka FastAPI yang menyajikan API
(`/api`) dan SPA (statis) dalam satu proses, dengan `lifespan` untuk menyiapkan DB,
runtime, dan event bus.

## Tujuan
- Paket `telegent.web` berdiri dengan `create_app() -> FastAPI`.
- Endpoint `GET /healthz` publik.
- SPA statis dilayani di `/` (fallback ke `index.html` untuk routing SPA).
- `lifespan` startup/shutdown memanggil komponen yang akan datang (DB, runtime, bus)
  via placeholder yang aman.

## Deliverable
- `src/telegent/web/__init__.py`
- `src/telegent/web/app.py` (`create_app`, konfigurasi middleware, router agregat,
  static mount)
- `src/telegent/web/deps.py` (placeholder dependency)
- `src/telegent/web/routers/health.py`

## Langkah implementasi
1. Tambah dependensi: `fastapi`, `uvicorn[standard]` ke `pyproject.toml`.
2. Buat `create_app()` dengan `lifespan` (async context manager).
3. Daftarkan router `/api/*` dan `StaticFiles`/fallback SPA.
4. `GET /api/healthz` → `{ok, version}` (versi dari `telegent.__version__`).
5. Tentukan lokasi build SPA (mis. `frontend/build` atau `src/telegent/web/static`);
   bila belum ada, tampilkan halaman placeholder minimal (agar Fase 0 dapat diuji).
6. Middleware keamanan dasar (header) — detail di A5.

## Kriteria terima (Definition of Done)
- [ ] `uv run python -c "from telegent.web.app import create_app; create_app()"` berhasil.
- [ ] `GET /api/healthz` mengembalikan 200 + JSON.
- [ ] `GET /` mengembalikan `index.html` (placeholder bila SPA belum dibangun).
- [ ] `uv run pyright src/telegent` hijau.
- [ ] Uji minimal `TestClient` untuk `healthz` (boleh di H1, minimal smoke di sini).

## Catatan teknis / pertanyaan
- Q6/Q7 (SvelteKit/Svelte) memengaruhi lokasi artefak build; gunakan path konfigurabel.
