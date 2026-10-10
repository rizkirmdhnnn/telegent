"""Tipe data untuk sistem tool calling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Union

# Handler tool: menerima (konteks, argumen) dan mengembalikan dict hasil.
# Boleh sinkron (dict) maupun asinkron (coroutine).
ToolHandler = Callable[
    ["ToolContext", dict[str, Any]], Union[dict[str, Any], Awaitable[dict[str, Any]]]
]

#: Membangun ulang `ToolSpec` dari konfigurasi tersimpan (mis. zona waktu default).
#: Dipakai registry agar registry tidak perlu mengenal nama tool konkret.
ToolConfigFactory = Callable[[dict[str, Any]], "ToolSpec"]


#: Status eksekusi tool (spesifikasi §5.7 `tool_call_record.status`).
TOOL_STATUS_OK = "ok"
TOOL_STATUS_ERROR = "error"
TOOL_STATUS_TIMEOUT = "timeout"
TOOL_STATUS_CANCELLED = "cancelled"


@dataclass
class ToolContext:
    """Konteks eksekusi tool (identitas sesi + aksi yang diizinkan)."""

    user_id: int
    call_id: int
    logger: Any = None
    # Aksi untuk mengakhiri panggilan (disediakan CallSession). Sinkron: hanya
    # menjadwalkan, agar handler tool tidak memblokir penerimaan.
    hangup: Callable[[], None] | None = None


@dataclass
class ToolSpec:
    """Deklarasi satu tool beserta handler-nya."""

    name: str
    description: str
    handler: ToolHandler
    parameters_json_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    timeout: float = 5.0
    behavior: str = "BLOCKING"  # "BLOCKING" | "NON_BLOCKING"
    can_disable: bool = True
    # Pabrik untuk membangun ulang spec dari konfigurasi yang tersimpan.
    config_factory: ToolConfigFactory | None = None


@dataclass
class ToolRequest:
    """Permintaan eksekusi tool dari model."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResponse:
    """Hasil eksekusi tool yang dikirim kembali ke model."""

    id: str
    name: str
    response: dict[str, Any]
    #: Status eksekusi untuk observability (spesifikasi §5.7):
    #: `ok`/`error`/`timeout`/`cancelled`.
    status: str = TOOL_STATUS_OK
