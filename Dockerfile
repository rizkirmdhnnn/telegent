# Telegent - image runtime untuk AI voice agent panggilan Telegram (berbasis uv)
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TELEGRAM_SESSION_DIR=/data

WORKDIR /app

# Pasang dependensi dulu (layer di-cache selama pyproject/uv.lock tidak berubah).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Salin sumber lalu pasang project.
COPY src ./src
RUN uv sync --frozen --no-dev

# Direktori sesi Telegram (di-mount sebagai volume).
RUN mkdir -p /data

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["telegent"]
