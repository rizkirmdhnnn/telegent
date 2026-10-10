"""Tipe data untuk sistem tool calling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Union

# Handler tool: menerima (konteks, argumen) dan mengembalikan dict hasil.
# Boleh sinkron (dict) maupun asinkron (coroutine).
ToolHandler = Callable[
    ["ToolContext", dict[str, Any]], Union[dict[str, Any], Awaitable[dict[str, Any]]]
]


@dataclass
class ToolContext:
    """Konteks eksekusi tool (identitas sesi)."""

    user_id: int
    call_id: int
    logger: Any = None


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
