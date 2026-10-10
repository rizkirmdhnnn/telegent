"""Registry seluruh setting web panel: tipe, validasi, dan cara penerapan.

Registry ini adalah satu-satunya sumber kebenaran tentang metadata setting
(label, tipe, rentang, kelompok, dan apakah perlu restart saat diubah).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from telegent.ai.prompt import (
    DEFAULT_GREETING_PROMPT,
    DEFAULT_IDLE_FAREWELL,
    DEFAULT_IDLE_PROMPT,
    DEFAULT_SYSTEM_INSTRUCTION,
)
from telegent.config import DEFAULT_GEMINI_MODEL


class SettingType(str, Enum):
    """Tipe nilai setting (dipakai juga untuk memilih kontrol di UI)."""

    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    TEXT = "text"
    TEXTAREA = "textarea"
    SECRET = "secret"
    INT_LIST = "int_list"
    ENUM = "enum"


class ApplyMode(str, Enum):
    """Cara sebuah setting diterapkan ke runtime."""

    HOT = "hot"  # berlaku untuk panggilan baru, tanpa restart
    RESTART = "restart"  # perlu restart klien runtime
    BOOTSTRAP = "bootstrap"  # hanya dari environment, di luar UI


class Group(str, Enum):
    """Kelompok tampilan di halaman pengaturan."""

    KREDENSIAL = "kredensial"
    AKUN_TELEGRAM = "akun_telegram"
    MODEL_AI = "model_ai"
    PERSONA = "persona"
    KEBIJAKAN_AKSES = "kebijakan_akses"
    ANTI_IDLE = "anti_idle"
    LOGGING = "logging"
    APLIKASI = "aplikasi"
    AUDIO = "audio"


class SettingValidationError(ValueError):
    """Nilai setting tidak valid."""

    def __init__(self, key: str, code: str, **params: Any) -> None:
        super().__init__(f"{key}: {code}")
        self.key = key
        self.code = code
        self.params: dict[str, Any] = params

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "key": self.key, **self.params}


class SettingsValidationError(ValueError):
    """Kumpulan galat validasi dari satu permintaan perubahan."""

    def __init__(self, errors: list[SettingValidationError]) -> None:
        super().__init__("Pengaturan tidak valid.")
        self.errors = errors

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {err.key: {"code": err.code, **err.params} for err in self.errors}


def _invalid(key: str, code: str, **params: Any) -> SettingValidationError:
    return SettingValidationError(key, code, **params)


@dataclass(frozen=True)
class SettingSpec:
    """Metadata satu setting."""

    key: str
    type: SettingType
    group: Group
    apply: ApplyMode
    default: Any
    label: str = ""
    description: str = ""
    secret: bool = False
    advanced: bool = False
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: bool = False
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    enum_case_sensitive: bool = True

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", f"settings.{self.key}")
        if not self.description:
            object.__setattr__(self, "description", f"settings.{self.key}.help")

    # ------------------------------------------------------------ coercion

    def coerce(self, raw: Any) -> Any:
        """Ubah & validasi nilai mentah menjadi tipe setting ini."""
        if self.type is SettingType.BOOL:
            value = self._coerce_bool(raw)
        elif self.type is SettingType.INT:
            value = self._coerce_int(raw)
        elif self.type is SettingType.FLOAT:
            value = self._coerce_float(raw)
        elif self.type is SettingType.INT_LIST:
            value = self._coerce_int_list(raw)
        elif self.type in (SettingType.TEXT, SettingType.TEXTAREA, SettingType.SECRET):
            value = self._coerce_str(raw)
        else:  # ENUM
            value = self._coerce_enum(raw)

        self._validate_bounds(value)
        return value

    def _coerce_bool(self, raw: Any) -> bool:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        if isinstance(raw, int) and raw in (0, 1):
            return bool(raw)
        raise _invalid(self.key, "invalid_bool")

    def _coerce_int(self, raw: Any) -> int:
        if isinstance(raw, bool):
            raise _invalid(self.key, "invalid_int")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float) and raw.is_integer():
            return int(raw)
        if isinstance(raw, str) and raw.strip():
            try:
                return int(raw.strip())
            except ValueError:
                pass
        raise _invalid(self.key, "invalid_int")

    def _coerce_float(self, raw: Any) -> float:
        if isinstance(raw, bool):
            raise _invalid(self.key, "invalid_float")
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str) and raw.strip():
            try:
                return float(raw.strip())
            except ValueError:
                pass
        raise _invalid(self.key, "invalid_float")

    def _coerce_str(self, raw: Any) -> str:
        if not isinstance(raw, str):
            raise _invalid(self.key, "invalid_string")
        if self.min_length is not None and len(raw.strip()) < self.min_length:
            raise _invalid(self.key, "too_short", min_length=self.min_length)
        if self.max_length is not None and len(raw) > self.max_length:
            raise _invalid(self.key, "too_long", max_length=self.max_length)
        if self.pattern and not re.fullmatch(self.pattern, raw.strip()):
            raise _invalid(self.key, "invalid_format")
        return raw.strip() if self.type is not SettingType.TEXTAREA else raw

    def _coerce_int_list(self, raw: Any) -> list[int]:
        if raw is None:
            return []
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.replace(";", ",").split(",")]
            parts = [p for p in parts if p]
        elif isinstance(raw, (list, tuple)):
            parts = [str(p).strip() for p in raw]
        else:
            raise _invalid(self.key, "invalid_int_list")

        hasil: list[int] = []
        for part in parts:
            try:
                hasil.append(int(part))
            except ValueError:
                raise _invalid(self.key, "invalid_int_list", value=part) from None
        return hasil

    def _coerce_enum(self, raw: Any) -> str:
        if not isinstance(raw, str):
            raise _invalid(self.key, "invalid_choice", choices=list(self.choices))
        candidate = raw.strip() if self.enum_case_sensitive else raw.strip().upper()
        for choice in self.choices:
            if choice == candidate or (
                not self.enum_case_sensitive and choice.upper() == candidate.upper()
            ):
                return choice
        raise _invalid(self.key, "invalid_choice", choices=list(self.choices))

    def _validate_bounds(self, value: Any) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None:
                if self.exclusive_minimum and value <= self.minimum:
                    raise _invalid(self.key, "too_small", minimum=self.minimum)
                if not self.exclusive_minimum and value < self.minimum:
                    raise _invalid(self.key, "too_small", minimum=self.minimum)
        if self.maximum is not None and isinstance(value, (int, float)):
            if value > self.maximum:
                raise _invalid(self.key, "too_large", maximum=self.maximum)

    # ---------------------------------------------------------------- meta

    def to_schema(self) -> dict[str, Any]:
        """Metadata untuk UI (tanpa nilai default yang sensitif)."""
        return {
            "key": self.key,
            "type": self.type.value,
            "group": self.group.value,
            "apply": self.apply.value,
            "label": self.label,
            "description": self.description,
            "secret": self.secret,
            "advanced": self.advanced,
            "choices": list(self.choices),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "exclusive_minimum": self.exclusive_minimum,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "has_default": self.default not in (None, [], ""),
        }


def _specs() -> tuple[SettingSpec, ...]:
    return (
        # --- Kredensial (restart) ---
        SettingSpec(
            key="telegram_api_id",
            type=SettingType.INT,
            group=Group.KREDENSIAL,
            apply=ApplyMode.RESTART,
            default=0,
            minimum=1,
        ),
        SettingSpec(
            key="telegram_api_hash",
            type=SettingType.TEXT,
            group=Group.KREDENSIAL,
            apply=ApplyMode.RESTART,
            default="",
            pattern=r"[0-9a-fA-F]{32}",
            secret=True,
        ),
        SettingSpec(
            key="gemini_api_key",
            type=SettingType.SECRET,
            group=Group.KREDENSIAL,
            apply=ApplyMode.RESTART,
            default="",
            min_length=20,
            secret=True,
        ),
        # --- Akun Telegram ---
        SettingSpec(
            key="telegram_session_name",
            type=SettingType.TEXT,
            group=Group.AKUN_TELEGRAM,
            apply=ApplyMode.RESTART,
            default="userbot_session",
            pattern=r"[A-Za-z0-9_.-]{1,64}",
        ),
        # --- Model AI ---
        SettingSpec(
            key="gemini_model",
            type=SettingType.TEXT,
            group=Group.MODEL_AI,
            apply=ApplyMode.HOT,
            default=DEFAULT_GEMINI_MODEL,
            min_length=3,
            max_length=120,
        ),
        # --- Persona (hot) ---
        SettingSpec(key="system_instruction", type=SettingType.TEXTAREA, group=Group.PERSONA, apply=ApplyMode.HOT, default=DEFAULT_SYSTEM_INSTRUCTION),
        SettingSpec(key="greeting_prompt", type=SettingType.TEXTAREA, group=Group.PERSONA, apply=ApplyMode.HOT, default=DEFAULT_GREETING_PROMPT),
        SettingSpec(key="idle_prompt_instruction", type=SettingType.TEXTAREA, group=Group.PERSONA, apply=ApplyMode.HOT, default=DEFAULT_IDLE_PROMPT),
        SettingSpec(key="idle_farewell_instruction", type=SettingType.TEXTAREA, group=Group.PERSONA, apply=ApplyMode.HOT, default=DEFAULT_IDLE_FAREWELL),
        # --- Kebijakan akses (hot) ---
        SettingSpec(key="allowed_user_ids", type=SettingType.INT_LIST, group=Group.KEBIJAKAN_AKSES, apply=ApplyMode.HOT, default=[]),
        SettingSpec(key="max_concurrent_calls", type=SettingType.INT, group=Group.KEBIJAKAN_AKSES, apply=ApplyMode.HOT, default=4, minimum=1, maximum=1000),
        SettingSpec(key="max_call_duration", type=SettingType.FLOAT, group=Group.KEBIJAKAN_AKSES, apply=ApplyMode.HOT, default=600.0, minimum=0, maximum=86400),
        SettingSpec(key="max_calls_per_window", type=SettingType.INT, group=Group.KEBIJAKAN_AKSES, apply=ApplyMode.HOT, default=5, minimum=0, maximum=10000),
        SettingSpec(key="call_window_seconds", type=SettingType.FLOAT, group=Group.KEBIJAKAN_AKSES, apply=ApplyMode.HOT, default=60.0, minimum=0, exclusive_minimum=True, maximum=86400),
        # --- Anti-idle (hot) ---
        SettingSpec(key="idle_enabled", type=SettingType.BOOL, group=Group.ANTI_IDLE, apply=ApplyMode.HOT, default=True),
        SettingSpec(key="idle_prompt_seconds", type=SettingType.FLOAT, group=Group.ANTI_IDLE, apply=ApplyMode.HOT, default=15.0, minimum=0, exclusive_minimum=True, maximum=600),
        SettingSpec(key="idle_hangup_seconds", type=SettingType.FLOAT, group=Group.ANTI_IDLE, apply=ApplyMode.HOT, default=15.0, minimum=0, exclusive_minimum=True, maximum=600),
        # --- Logging (hot) ---
        SettingSpec(
            key="log_level",
            type=SettingType.ENUM,
            group=Group.LOGGING,
            apply=ApplyMode.HOT,
            default="INFO",
            choices=("DEBUG", "INFO", "WARNING", "ERROR"),
            enum_case_sensitive=False,
        ),
        # --- Aplikasi (hot) ---
        SettingSpec(key="bot_autostart", type=SettingType.BOOL, group=Group.APLIKASI, apply=ApplyMode.HOT, default=True),
        SettingSpec(key="calls_retention_days", type=SettingType.INT, group=Group.APLIKASI, apply=ApplyMode.HOT, default=30, minimum=0, maximum=3650),
        SettingSpec(key="transcripts_retention_days", type=SettingType.INT, group=Group.APLIKASI, apply=ApplyMode.HOT, default=30, minimum=0, maximum=3650),
        SettingSpec(key="store_transcripts", type=SettingType.BOOL, group=Group.APLIKASI, apply=ApplyMode.HOT, default=True),
        SettingSpec(key="log_buffer_lines", type=SettingType.INT, group=Group.APLIKASI, apply=ApplyMode.HOT, default=1000, minimum=100, maximum=10000),
        # --- Audio lanjutan (restart, disembunyikan di UI) ---
        SettingSpec(key="tg_sample_rate", type=SettingType.INT, group=Group.AUDIO, apply=ApplyMode.RESTART, default=48000, advanced=True),
        SettingSpec(key="tg_frame_ms", type=SettingType.INT, group=Group.AUDIO, apply=ApplyMode.RESTART, default=10, advanced=True),
        SettingSpec(key="gemini_input_rate", type=SettingType.INT, group=Group.AUDIO, apply=ApplyMode.RESTART, default=16000, advanced=True),
        SettingSpec(key="gemini_output_rate", type=SettingType.INT, group=Group.AUDIO, apply=ApplyMode.RESTART, default=24000, advanced=True),
    )


REGISTRY: dict[str, SettingSpec] = {spec.key: spec for spec in _specs()}

#: Setting yang tidak boleh kosong bila runtime dijalankan.
REQUIRED_KEYS = ("telegram_api_id", "telegram_api_hash", "gemini_api_key")


def get_spec(key: str) -> SettingSpec | None:
    return REGISTRY.get(key)


def specs_by_group() -> dict[str, list[SettingSpec]]:
    """Kelompokkan setting untuk tampilan UI (urutan stabil)."""
    grouped: dict[str, list[SettingSpec]] = {}
    for spec in REGISTRY.values():
        grouped.setdefault(spec.group.value, []).append(spec)
    return grouped


def defaults() -> dict[str, Any]:
    """Nilai default seluruh setting."""
    return {key: spec.default for key, spec in REGISTRY.items()}