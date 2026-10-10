"""Konfigurasi aplikasi (terpusat, tervalidasi, dari environment / .env)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from telegent.ai.prompt import DEFAULT_GREETING_PROMPT, DEFAULT_SYSTEM_INSTRUCTION

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-live-preview"


class Settings(BaseSettings):
    """Semua konfigurasi runtime. Nama env var = nama field (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Kredensial (wajib) ---
    telegram_api_id: int
    telegram_api_hash: str
    gemini_api_key: str

    # --- Sesi Telegram ---
    telegram_session_name: str = "userbot_session"
    session_dir: str = "."

    # --- Gemini Live ---
    gemini_model: str = DEFAULT_GEMINI_MODEL
    system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION
    greeting_prompt: str = DEFAULT_GREETING_PROMPT

    # --- Kebijakan akses & beban ---
    allowed_user_ids: str = ""
    max_concurrent_calls: int = Field(default=4, ge=1)

    # --- Logging ---
    log_level: str = "INFO"

    # --- Audio (parameter Telegram VoIP & Gemini) ---
    tg_sample_rate: int = 48000
    tg_frame_ms: int = 10
    gemini_input_rate: int = 16000
    gemini_output_rate: int = 24000

    @property
    def allowed_user_id_set(self) -> set[int]:
        """Parse daftar ID (dipisah koma/titik-koma) dari env ALLOWED_USER_IDS."""
        ids: set[int] = set()
        for part in self.allowed_user_ids.replace(";", ",").split(","):
            part = part.strip()
            if part:
                ids.add(int(part))
        return ids

    @property
    def session_workdir(self) -> Path:
        """Direktori tempat file *.session Pyrogram disimpan (mis. /data di Docker)."""
        path = Path(self.session_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def tg_frame_bytes(self) -> int:
        """Ukuran satu frame audio Telegram (10 ms) dalam byte: 48000 * 0.01 * 2 = 960."""
        return int(self.tg_sample_rate * (self.tg_frame_ms / 1000.0) * 2)
