"""Tool bawaan Telegent."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegent.ai.tools.spec import ToolContext, ToolSpec

DEFAULT_TIMEZONE = "Asia/Jakarta"


async def _get_current_datetime(ctx: ToolContext, args: dict) -> dict:
    tz_name = (args.get("timezone") or DEFAULT_TIMEZONE).strip()
    try:
        zone = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - fallback ke zona default
        tz_name = DEFAULT_TIMEZONE
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    now = datetime.now(zone)
    return {
        "iso": now.isoformat(),
        "human": now.strftime("%A, %d %B %Y %H:%M"),
        "timezone": tz_name,
    }


def make_datetime_tool() -> ToolSpec:
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
        handler=_get_current_datetime,
        timeout=2.0,
        behavior="BLOCKING",
    )


def default_tools() -> list[ToolSpec]:
    """Kumpulan tool bawaan untuk PoC tool calling."""
    return [make_datetime_tool()]
