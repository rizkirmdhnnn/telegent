"""Penyimpanan konfigurasi: database sebagai sumber kebenaran.

Nilai setting disimpan pada tabel `app_setting` (JSON, atau ciphertext untuk
secret). `build_settings()` menyusun objek `telegent.config.Settings` yang dipakai
runtime, menggabungkan nilai tersimpan dengan default registry.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telegent.config import Settings
from telegent.web.crypto import SecretCipher, mask
from telegent.web.db import models
from telegent.web.db.base import Database
from telegent.web.settings_registry import (
    REGISTRY,
    REQUIRED_KEYS,
    ApplyMode,
    SettingSpec,
    SettingValidationError,
    SettingsValidationError,
    specs_by_group,
)

log = logging.getLogger("telegent.web.settings")

SYSTEM_ACTOR = "system"


class NotConfigured(RuntimeError):
    """Konfigurasi belum cukup untuk menjalankan bot."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"Konfigurasi belum lengkap: {', '.join(missing)}")
        self.missing = missing


@dataclass
class UpdateResult:
    """Hasil perubahan setting: mana yang langsung berlaku, mana yang perlu restart."""

    applied: list[str] = field(default_factory=list)
    needs_restart: list[str] = field(default_factory=list)


def _settings_field_names() -> set[str]:
    return set(Settings.model_fields.keys())


class SettingsStore:
    """Baca/tulis konfigurasi platform di database."""

    def __init__(self, db: Database, cipher: SecretCipher) -> None:
        self._db = db
        self._cipher = cipher
        self._settings_fields = _settings_field_names()

    # --------------------------------------------------------------- reading

    async def _load_rows(self, session: AsyncSession) -> dict[str, tuple[str, bool]]:
        rows = (await session.execute(select(models.AppSetting))).scalars().all()
        return {row.key: (row.value, row.encrypted) for row in rows}

    def _decode(self, raw: str, encrypted: bool, spec: SettingSpec) -> Any:
        if encrypted:
            plaintext = self._cipher.decrypt(raw)
        else:
            plaintext = raw
        try:
            return json.loads(plaintext)
        except json.JSONDecodeError:
            log.warning("Nilai setting '%s' rusak; memakai default.", spec.key)
            return spec.default

    async def load_values(self) -> dict[str, Any]:
        """Semua nilai setting (default registry + nilai tersimpan, terdekripsi)."""
        values = {key: spec.default for key, spec in REGISTRY.items()}
        async with self._db.session() as session:
            rows = await self._load_rows(session)
        for key, (raw, encrypted) in rows.items():
            spec = REGISTRY.get(key)
            if spec is None:
                log.warning("Setting '%s' tidak dikenal di registry; diabaikan.", key)
                continue
            values[key] = self._decode(raw, encrypted, spec)
        return values

    async def get(self, key: str) -> Any:
        """Nilai satu setting (terdekripsi bila secret)."""
        spec = REGISTRY.get(key)
        if spec is None:
            raise KeyError(key)
        values = await self.load_values()
        return values[key]

    async def is_configured(self) -> bool:
        """True bila seluruh kredensial wajib sudah terisi."""
        values = await self.load_values()
        return all(values.get(key) not in (None, "", 0, []) for key in REQUIRED_KEYS)

    async def missing_required(self) -> list[str]:
        values = await self.load_values()
        return [
            key
            for key in REQUIRED_KEYS
            if values.get(key) in (None, "", 0, [])
        ]

    # --------------------------------------------------------------- writing

    async def _upsert(
        self, session: AsyncSession, key: str, value: Any, actor: str
    ) -> None:
        spec = REGISTRY[key]
        payload = json.dumps(value, ensure_ascii=False)
        encrypted = spec.secret
        if encrypted:
            payload = self._cipher.encrypt(payload)

        row = await session.get(models.AppSetting, key)
        if row is None:
            session.add(
                models.AppSetting(
                    key=key, value=payload, encrypted=encrypted, updated_by=actor
                )
            )
            return
        row.value = payload
        row.encrypted = encrypted
        row.updated_by = actor

    async def update(self, changes: dict[str, Any], actor: str = SYSTEM_ACTOR) -> UpdateResult:
        """Simpan perubahan setting (validasi penuh sebelum menulis)."""
        errors: list[SettingValidationError] = []
        prepared: dict[str, Any] = {}
        for key, raw in changes.items():
            spec = REGISTRY.get(key)
            if spec is None:
                errors.append(SettingValidationError(key, "unknown_key"))
                continue
            try:
                prepared[key] = spec.coerce(raw)
            except SettingValidationError as exc:
                errors.append(exc)

        if errors:
            raise SettingsValidationError(errors)

        async with self._db.session() as session:
            for key, value in prepared.items():
                await self._upsert(session, key, value, actor)

        log.info("Setting diperbarui oleh %s: %s", actor, ", ".join(sorted(prepared)))
        return UpdateResult(
            applied=[k for k, s in REGISTRY.items() if k in prepared and s.apply is ApplyMode.HOT],
            needs_restart=[k for k, s in REGISTRY.items() if k in prepared and s.apply is ApplyMode.RESTART],
        )

    async def reset_to_default(self, keys: list[str], actor: str = SYSTEM_ACTOR) -> UpdateResult:
        """Hapus nilai tersimpan agar kembali ke default registry."""
        prepared = {}
        for key in keys:
            spec = REGISTRY.get(key)
            if spec is None:
                continue
            prepared[key] = spec.default

        async with self._db.session() as session:
            for key in prepared:
                row = await session.get(models.AppSetting, key)
                if row is not None:
                    await session.delete(row)

        return UpdateResult(
            applied=[k for k, s in REGISTRY.items() if k in prepared and s.apply is ApplyMode.HOT],
            needs_restart=[k for k, s in REGISTRY.items() if k in prepared and s.apply is ApplyMode.RESTART],
        )

    # -------------------------------------------------------------- runtime

    def _to_settings_kwargs(self, values: dict[str, Any]) -> dict[str, Any]:
        """Petakan nilai registry ke field `Settings` (abaikan key khusus aplikasi)."""
        kwargs = {
            key: value
            for key, value in values.items()
            if key in self._settings_fields
        }
        # `allowed_user_ids` disimpan sebagai list[int], Settings mengharapkan string.
        if isinstance(kwargs.get("allowed_user_ids"), list):
            kwargs["allowed_user_ids"] = ",".join(
                str(item) for item in kwargs["allowed_user_ids"]
            )
        return kwargs

    async def build_settings(self) -> Settings:
        """Susun `Settings` dari DB + default; lempar `NotConfigured` bila kurang."""
        values = await self.load_values()
        missing = [
            key
            for key in REQUIRED_KEYS
            if values.get(key) in (None, "", 0, [])
        ]
        if missing:
            raise NotConfigured(missing)

        kwargs = self._to_settings_kwargs(values)
        try:
            # `model_validate` deliberate: nilai murni dari DB, bukan env/.env.
            return Settings.model_validate(kwargs)
        except Exception as exc:  # noqa: BLE001 - validasi pydantic
            raise NotConfigured([]) from exc

    async def restart_keys_pending(self, current: Settings | None) -> list[str]:
        """Setting kelas `restart` yang tersimpan tetapi belum dipakai runtime."""
        values = await self.load_values()
        async with self._db.session() as session:
            stored = set((await self._load_rows(session)).keys())

        pending: list[str] = []
        for key, spec in REGISTRY.items():
            if spec.apply is not ApplyMode.RESTART:
                continue
            if current is None:
                if key in stored:
                    pending.append(key)
                continue
            if key not in self._settings_fields:
                # Parameter lanjutan tidak dibaca runtime; tetap perlu restart.
                if key in stored:
                    pending.append(key)
                continue
            if _differs(getattr(current, key, None), values[key], spec):
                pending.append(key)
        return pending

    # ------------------------------------------------------------------ UI

    async def schema(self) -> list[dict[str, Any]]:
        """Metadata seluruh setting untuk membangun form UI."""
        return [spec.to_schema() for spec in REGISTRY.values()]

    async def list_for_ui(self) -> list[dict[str, Any]]:
        """Daftar setting bergrup; nilai secret disamarkan."""
        values = await self.load_values()
        async with self._db.session() as session:
            stored = set((await self._load_rows(session)).keys())

        grouped: list[dict[str, Any]] = []
        for group, specs in specs_by_group().items():
            items: list[dict[str, Any]] = []
            for spec in specs:
                value = values.get(spec.key)
                items.append(
                    {
                        "key": spec.key,
                        "type": spec.type.value,
                        "apply": spec.apply.value,
                        "secret": spec.secret,
                        "advanced": spec.advanced,
                        "is_set": spec.key in stored,
                        "value": mask(value) if spec.secret else value,
                    }
                )
            grouped.append({"group": group, "items": items})
        return grouped

    # ------------------------------------------------------------- migrasi

    async def import_env_once(self) -> int:
        """Impor nilai dari `.env` lama bila database masih kosong (satu kali)."""
        async with self._db.session() as session:
            if await self._load_rows(session):
                return 0

        try:
            legacy = Settings()  # pyright: ignore[reportCallIssue]  # baca .env + env
        except Exception:  # noqa: BLE001 - .env lama belum lengkap
            log.info("Tidak ada konfigurasi .env lama untuk diimpor.")
            return 0

        legacy_values = legacy.model_dump()
        changes: dict[str, Any] = {}
        for key, spec in REGISTRY.items():
            if key not in legacy_values:
                continue
            value = legacy_values[key]
            try:
                coerced = spec.coerce(value)
            except SettingValidationError:
                continue
            if coerced != spec.default:
                changes[key] = coerced

        if not changes:
            return 0

        await self.update(changes, actor=SYSTEM_ACTOR)
        log.info("Mengimpor %d setting dari konfigurasi .env lama.", len(changes))
        return len(changes)


def _differs(current: Any, stored: Any, spec: SettingSpec) -> bool:
    """Bandingkan nilai runtime dengan nilai tersimpan secara aman terhadap tipe."""
    if current is None and stored in (None, "", []):
        return False
    try:
        normalized = spec.coerce(current)
    except SettingValidationError:
        return True
    if isinstance(normalized, float) or isinstance(stored, float):
        try:
            return abs(float(normalized) - float(stored)) > 1e-9
        except (TypeError, ValueError):
            return True
    return normalized != stored