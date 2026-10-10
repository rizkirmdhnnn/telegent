"""Tool bawaan Telegent."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegent.ai.tools.spec import ToolContext, ToolSpec

DEFAULT_TIMEZONE = "Asia/Jakarta"


def make_datetime_tool(default_timezone: str = DEFAULT_TIMEZONE) -> ToolSpec:
    """Tool jam; `default_timezone` dipakai bila model tidak mengirim zona waktu."""

    def _from_config(config: dict) -> ToolSpec:
        return make_datetime_tool(
            default_timezone=str(config.get("default_timezone") or DEFAULT_TIMEZONE)
        )

    async def _handler(ctx: ToolContext, args: dict) -> dict:
        del ctx
        tz_name = (args.get("timezone") or default_timezone).strip()
        try:
            zone = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001 - zona dari model mungkin tidak dikenal
            # Fallback bertingkat: zona yang dikonfigurasi, lalu konstanta bawaan.
            tz_name = default_timezone
            try:
                zone = ZoneInfo(default_timezone)
            except Exception:  # noqa: BLE001 - konfigurasi pun tidak valid
                tz_name = DEFAULT_TIMEZONE
                zone = ZoneInfo(DEFAULT_TIMEZONE)
        now = datetime.now(zone)
        return {
            "iso": now.isoformat(),
            "human": now.strftime("%A, %d %B %Y %H:%M"),
            "timezone": tz_name,
        }

    return ToolSpec(
        name="get_current_datetime",
        description=(
            "Mengambil tanggal dan waktu saat ini. Gunakan saat penelpon menanyakan "
            "hari, tanggal, atau jam. Opsional tentukan zona waktu IANA (mis. Asia/Jakarta)."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Nama zona waktu IANA, contoh: Asia/Jakarta",
                }
            },
        },
        handler=_handler,
        timeout=2.0,
        behavior="BLOCKING",
        config_factory=_from_config,
    )


def make_end_call_tool() -> ToolSpec:
    return ToolSpec(
        name="end_call",
        description=(
            "Mengakhiri panggilan telepon. Gunakan HANYA ketika penelpon secara jelas "
            "ingin mengakhiri percakapan atau mengucapkan salam perpisahan. "
            "Ucapkan pamitan singkat terlebih dahulu, baru panggil fungsi ini."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Alasan singkat mengakhiri panggilan (opsional).",
                }
            },
        },
        handler=_end_call,
        timeout=2.0,
        behavior="BLOCKING",
        can_disable=False,
    )


async def _end_call(ctx: ToolContext, args: dict) -> dict:
    if ctx.hangup is None:
        return {"error": "Fitur mengakhiri panggilan tidak tersedia pada sesi ini."}
    reason = (args.get("reason") or "").strip()
    ctx.hangup()
    result: dict = {"status": "ending_call"}
    if reason:
        result["reason"] = reason
    return result


def default_tools() -> list[ToolSpec]:
    """Kumpulan tool bawaan untuk PoC tool calling."""
    return [make_datetime_tool(), make_end_call_tool()]
