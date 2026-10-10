"""Gabungkan kunci i18n baru (label setting, pesan kredensial, galat).

Dijalankan sekali untuk menyelaraskan id.json & en.json.
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "src" / "lib" / "i18n"

LABELS_ID = {
    "telegram_api_id": "Telegram API ID",
    "telegram_api_hash": "Telegram API Hash",
    "gemini_api_key": "Gemini API Key",
    "telegram_session_name": "Nama Sesi Telegram",
    "gemini_model": "Model Gemini",
    "system_instruction": "Instruksi Sistem",
    "greeting_prompt": "Sapaan Awal",
    "idle_prompt_instruction": "Instruksi Konfirmasi (Anti-idle)",
    "idle_farewell_instruction": "Instruksi Pamitan (Anti-idle)",
    "allowed_user_ids": "ID Telegram yang Diizinkan",
    "max_concurrent_calls": "Panggilan Bersamaan Maksimum",
    "max_call_duration": "Durasi Panggilan Maksimum",
    "max_calls_per_window": "Batas Panggilan per Jendela",
    "call_window_seconds": "Panjang Jendela Rate-limit",
    "idle_enabled": "Aktifkan Anti-idle",
    "idle_prompt_seconds": "Jeda Diam sebelum Konfirmasi",
    "idle_hangup_seconds": "Jeda Diam sebelum Akhiri",
    "log_level": "Level Log",
    "bot_autostart": "Jalankan Bot Saat Boot",
    "calls_retention_days": "Retensi Riwayat Panggilan",
    "transcripts_retention_days": "Retensi Transkrip",
    "store_transcripts": "Simpan Transkrip",
    "log_buffer_lines": "Baris Log Buffer",
    "tg_sample_rate": "Sample Rate Telegram",
    "tg_frame_ms": "Durasi Frame Telegram",
    "gemini_input_rate": "Sample Rate Input Gemini",
    "gemini_output_rate": "Sample Rate Output Gemini",
}

LABELS_EN = {
    "telegram_api_id": "Telegram API ID",
    "telegram_api_hash": "Telegram API Hash",
    "gemini_api_key": "Gemini API Key",
    "telegram_session_name": "Telegram Session Name",
    "gemini_model": "Gemini Model",
    "system_instruction": "System Instruction",
    "greeting_prompt": "Greeting Prompt",
    "idle_prompt_instruction": "Idle Check-in Instruction",
    "idle_farewell_instruction": "Idle Farewell Instruction",
    "allowed_user_ids": "Allowed Telegram IDs",
    "max_concurrent_calls": "Max Concurrent Calls",
    "max_call_duration": "Max Call Duration",
    "max_calls_per_window": "Calls per Window Limit",
    "call_window_seconds": "Rate-limit Window Length",
    "idle_enabled": "Enable Anti-idle",
    "idle_prompt_seconds": "Idle Silence Before Check-in",
    "idle_hangup_seconds": "Idle Silence Before Hangup",
    "log_level": "Log Level",
    "bot_autostart": "Start Bot on Boot",
    "calls_retention_days": "Call History Retention",
    "transcripts_retention_days": "Transcript Retention",
    "store_transcripts": "Store Transcripts",
    "log_buffer_lines": "Log Buffer Lines",
    "tg_sample_rate": "Telegram Sample Rate",
    "tg_frame_ms": "Telegram Frame Duration",
    "gemini_input_rate": "Gemini Input Sample Rate",
    "gemini_output_rate": "Gemini Output Sample Rate",
}

HELP_ID = {
    "allowed_user_ids": "Kosongkan untuk menerima panggilan dari siapa saja.",
    "max_call_duration": " dalam detik; 0 berarti tanpa batas.",
    "max_calls_per_window": "Panggilan maksimum dari satu pengguna; 0 berarti tanpa batas.",
    "call_window_seconds": "Panjang jendela dalam detik untuk pembatasan di atas.",
    "calls_retention_days": "Hari sebelum riwayat panggilan dihapus otomatis; 0 berarti disimpan selamanya.",
    "transcripts_retention_days": "Hari sebelum transkrip dihapus otomatis; 0 berarti disimpan selamanya.",
    "store_transcripts": "Matikan bila transkrip percakapan tidak boleh disimpan.",
    "system_instruction": "Persona dan aturan bicara AI. Perubahan berlaku untuk panggilan berikutnya.",
    "telegram_session_name": "Nama berkas sesi; mengubahnya berarti harus membuat sesi baru.",
}

HELP_EN = {
    "allowed_user_ids": "Leave empty to accept calls from anyone.",
    "max_call_duration": " in seconds; 0 means no limit.",
    "max_calls_per_window": "Maximum calls from one user; 0 means no limit.",
    "call_window_seconds": "Window length in seconds for the limit above.",
    "calls_retention_days": "Days before call history is deleted automatically; 0 keeps forever.",
    "transcripts_retention_days": "Days before transcripts are deleted automatically; 0 keeps forever.",
    "store_transcripts": "Turn off if conversation transcripts must not be stored.",
    "system_instruction": "The AI's persona and speaking rules. Applies to subsequent calls.",
    "telegram_session_name": "Session file name; changing it requires a new session.",
}

CREDENTIALS_ID = {
    "saved": "Kredensial berhasil disimpan.",
    "valid": "Kredensial valid.",
    "telegram_api_id": "Telegram API ID",
    "telegram_api_hash": "Telegram API Hash",
    "gemini_api_key": "Gemini API Key",
    "gemini_key_hint": "Dapatkan kunci API dari Google AI Studio (disimpan terenkripsi at-rest).",
    "stored_hint": "Tersimpan di server.",
    "stored_placeholder": "•••••••• (tersimpan)",
    "leave_blank_hint": "Dikosongkan berarti nilai yang tersimpan dipertahankan.",
    "next_step": "Langkah selanjutnya",
    "next_step_desc": "Setelah kredensial Telegram valid, hubungkan akun Telegram pada halaman Telegram.",
    "invalid": {
        "missing_credentials": "Kredensial belum lengkap diisi.",
        "invalid_api_id": "API ID harus berupa angka positif.",
        "invalid_api_hash": "API Hash harus 32 karakter hex.",
        "invalid_api_key": "API Key terlalu pendek (minimal 20 karakter).",
        "unknown_kind": "Jenis kredensial tidak dikenal.",
    },
}

CREDENTIALS_EN = {
    "saved": "Credentials saved.",
    "valid": "Credentials are valid.",
    "telegram_api_id": "Telegram API ID",
    "telegram_api_hash": "Telegram API Hash",
    "gemini_api_key": "Gemini API Key",
    "gemini_key_hint": "Get an API key from Google AI Studio (stored encrypted at rest).",
    "stored_hint": "Stored on the server.",
    "stored_placeholder": "•••••••• (stored)",
    "leave_blank_hint": "Leave blank to keep the stored value.",
    "next_step": "Next step",
    "next_step_desc": "Once the Telegram credentials are valid, connect the account on the Telegram page.",
    "invalid": {
        "missing_credentials": "Credentials are incomplete.",
        "invalid_api_id": "API ID must be a positive number.",
        "invalid_api_hash": "API Hash must be 32 hex characters.",
        "invalid_api_key": "API Key is too short (at least 20 characters).",
        "unknown_kind": "Unknown credential kind.",
    },
}

SETTINGS_EXTRA_ID = {
    "applied": "Perubahan diterapkan.",
    "restart_pending_keys": "Pengaturan tertunda",
    "restart_pending_generic": "Beberapa pengaturan berlabel Perlu Restart telah diubah.",
}

SETTINGS_EXTRA_EN = {
    "applied": "Changes applied.",
    "restart_pending_keys": "Pending settings",
    "restart_pending_generic": "Some settings marked 'Needs Restart' were changed.",
}

ERRORS_ID = {
    "no_changes": "Tidak ada nilai baru untuk disimpan.",
    "runtime_unavailable": "Runtime bot belum siap.",
    "database_unavailable": "Database belum siap.",
    "store_unavailable": "Penyimpanan konfigurasi belum siap.",
    "tool_not_found": "Tool tidak ditemukan.",
    "cannot_disable_tool": "Tool esensial tidak dapat dinonaktifkan.",
    "already_setup": "Admin sudah pernah dibuat.",
    "password_too_short": "Kata sandi terlalu pendek (minimal 8 karakter).",
    "runtime_unavailable_state": "Runtime tidak tersedia.",
    "network_error": "Gagal terhubung ke server.",
}

ERRORS_EN = {
    "no_changes": "There is nothing new to save.",
    "runtime_unavailable": "The bot runtime is not ready.",
    "database_unavailable": "The database is not ready.",
    "store_unavailable": "The settings store is not ready.",
    "tool_not_found": "Tool not found.",
    "cannot_disable_tool": "This essential tool cannot be disabled.",
    "already_setup": "An administrator already exists.",
    "password_too_short": "Password is too short (at least 8 characters).",
    "runtime_unavailable_state": "Runtime is unavailable.",
    "network_error": "Could not reach the server.",
}

NAV_ID = {
    "telegram": "Telegram",
    "coming_soon": "Segera",
}

NAV_EN = {
    "telegram": "Telegram",
    "coming_soon": "Soon",
}


def build_labels(base: dict[str, str], help_text: dict[str, str]) -> dict[str, object]:
    labels: dict[str, object] = {}
    for key, label in base.items():
        entry: dict[str, object] = label
        if key in help_text:
            entry = {"__t": label, "help": help_text[key]}
        labels[key] = entry
    return labels


def flatten_labels(labels: dict[str, object]) -> dict[str, str]:
    """Ubah {"key": {"__t": "Label", "help": "..."}} menjadi {"key": "Label", "key.help": "..."}."""
    result: dict[str, str] = {}
    for key, value in labels.items():
        if isinstance(value, dict):
            result[key] = str(value.get("__t", key))
            for extra_key, extra_value in value.items():
                if extra_key == "__t":
                    continue
                result[f"{key}.{extra_key}"] = str(extra_value)
        else:
            result[key] = str(value)
    return result


def main() -> None:
    for name, labels, helps, extra in (
        ("id", LABELS_ID, HELP_ID, None),
        ("en", LABELS_EN, HELP_EN, None),
    ):
        path = BASE / f"{name}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["labels"] = flatten_labels(build_labels(labels, helps))
        data["credentials"].update(CREDENTIALS_ID if name == "id" else CREDENTIALS_EN)
        data["settings"].update(SETTINGS_EXTRA_ID if name == "id" else SETTINGS_EXTRA_EN)
        data["errors"].update(ERRORS_ID if name == "id" else ERRORS_EN)
        data["nav"].update(NAV_ID if name == "id" else NAV_EN)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{name}.json diperbarui ({len(data['labels'])} label)")


if __name__ == "__main__":
    main()