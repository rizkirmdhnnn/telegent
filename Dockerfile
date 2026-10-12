# Telegent — image runtime single-container: SPA (Node) + bot/panel (Python).
#
# Tiga tahap:
#   1. frontend — build SPA SvelteKit (Node hanya ada di tahap ini)
#   2. builder  — pasang dependensi Python ke .venv
#   3. runtime  — Python + .venv + hasil build SPA; tanpa Node, tanpa toolchain

# ---- Tahap 1: build SPA ----
FROM node:22-bookworm-slim AS frontend

WORKDIR /app/frontend

# Layer dependensi terpisah supaya cache tetap kena saat hanya source berubah.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---- Builder: siapkan .venv lengkap (butuh compiler untuk tgcrypto) ----
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# tgcrypto adalah ekstensi C -> butuh compiler saat tidak ada wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable


# ---- Runtime: hanya .venv + SPA, tanpa toolchain Node ----
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Satu direktori data untuk DB, *.session, dan .secret_key (G1).
    TELEGENT_DATA_DIR=/data \
    # SPA dilayani FastAPI dari path ini (lihat bootstrap._resolve_frontend_dist).
    TELEGENT_FRONTEND_DIST=/app/web

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Hasil build SPA; tidak ada Node di image ini.
COPY --from=frontend /app/frontend/build /app/web

# Direktori data (di-mount sebagai volume): telegent.db, *.session, .secret_key.
RUN mkdir -p /data

EXPOSE 8080

ENTRYPOINT ["telegent"]