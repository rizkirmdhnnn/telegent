# Tiket — Telegent Web Panel

Satu berkas per tiket. Setiap tiket berdiri sendiri dan dapat dipindahkan menjadi
issue tracker item.

## Template tiket

```markdown
# <ID> — <Judul>

- **Epic/Fase:** ...
- **Dependensi:** ...
- **Estimasi:** S/M/L/XL
- **Referensi:** spec §..., plan §...

## Konteks
Mengapa tiket ini ada.

## Tujuan
Hasil yang diinginkan (bullet).

## Deliverable
Daftar artefak (berkas/modul).

## Langkah implementasi
1. ...

## Kriteria terima (Definition of Done)
- [ ] ...

## Catatan teknis / pertanyaan
- Qn dari open-questions.md
```

## Indeks & peta dependensi

```
A1 ─┬─ A2 ─┬─ A4 ─┬─ C1 ─ C2
    │      │      ├─ C3 ─ C4
    │      │      └─ A4 ─ F1/F2
    │      ├─ A5 ─ B2
    │      ├─ A6
    │      ├─ A7 ── F1/F2
    │      ├─ A8 ── E3
    │      └─ D1 ─ D2 ─ D3
    └─ B1 ─┬─ B2
           ├─ B3
           └─ C2/C4/E3/F2/H2
A7 ── E1 ─ E2 ─ E3
G1, H1–H3 bergantung pada keseluruhan fitur di atas
```

| ID | Judul | Fase | Est |
|---|---|---|---|
| A1 | [Skeleton web FastAPI + mount SPA + healthz](A1-fastapi-skeleton.md) | 0 | M |
| A2 | [Lapisan DB SQLAlchemy async + model + Alembic](A2-database-layer.md) | 0 | L |
| A3 | [Crypto secret (kunci file + Fernet)](A3-secret-crypto.md) | 0 | S |
| A4 | [Settings registry + SettingsStore](A4-settings-store.md) | 0 | L |
| A5 | [Auth admin + setup + TOTP](A5-auth-and-setup.md) | 0 | L |
| A6 | [Audit log](A6-audit-log.md) | 0 | S |
| A7 | [Refactor TelegentApp + RuntimeController](A7-runtime-controller.md) | 0 | L |
| A8 | [EventBus + logging SSE](A8-event-bus-sse.md) | 0 | M |
| B1 | [Scaffold SvelteKit + shadcn + i18n](B1-sveltekit-scaffold.md) | 1 | L |
| B2 | [UI auth: setup/login/akun](B2-auth-ui.md) | 1 | M |
| B3 | [App shell (nav/layout/tema/bahasa)](B3-app-shell.md) | 1 | M |
| C1 | [API settings + schema](C1-settings-api.md) | 1 | M |
| C2 | [UI settings](C2-settings-ui.md) | 1 | L |
| C3 | [API kredensial + tool](C3-credentials-tools-api.md) | 1 | M |
| C4 | [UI kredensial + tool](C4-credentials-tools-ui.md) | 1 | M |
| D1 | [Layanan login Telegram programatik](D1-telegram-login-service.md) | 2 | L |
| D2 | [API akun & login Telegram](D2-telegram-api.md) | 2 | M |
| D3 | [UI login/akun Telegram](D3-telegram-ui.md) | 2 | M |
| E1 | [Hook persistensi (call/transkrip/tool)](E1-persistence-hooks.md) | 3 | L |
| E2 | [API pemantauan](E2-monitoring-api.md) | 3 | M |
| E3 | [UI pemantauan](E3-monitoring-ui.md) | 3 | L |
| F1 | [API kontrol runtime](F1-runtime-control-api.md) | 4 | M |
| F2 | [UI kontrol runtime + apply](F2-runtime-control-ui.md) | 4 | M |
| F3 | [Pembersihan retensi](F3-retention-cleaner.md) | 4 | S |
| G1 | [Packaging + CLI + docs](G1-packaging-cli-docs.md) | 5 | L |
| H1 | [Test backend](H1-backend-tests.md) | 5 | L |
| H2 | [Test frontend](H2-frontend-tests.md) | 5 | M |
| H3 | [E2E + CI](H3-e2e-ci.md) | 5 | L |
