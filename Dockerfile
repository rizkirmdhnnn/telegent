# Telegent - image runtime untuk AI voice agent panggilan Telegram
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TELEGRAM_SESSION_DIR=/data

WORKDIR /app

# Wheel ntgcalls bersifat manylinux; tidak butuh device audio (MediaSource.EXTERNAL).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Direktori sesi Telegram (di-mount sebagai volume).
RUN mkdir -p /data

ENTRYPOINT ["telegent"]
