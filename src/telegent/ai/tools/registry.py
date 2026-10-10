"""Registry tool: deklarasi ke Gemini + eksekusi dengan timeout & penanganan error."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Optional

from google.genai import types as genai_types

from telegent.ai.tools.spec import ToolContext, ToolRequest, ToolResponse, ToolSpec


class ToolRegistry:
    """Menyimpan ToolSpec dan mengeksekusinya dengan aman."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> "ToolRegistry":
        if spec.name in self._specs:
            raise ValueError(f"Tool '{spec.name}' sudah terdaftar")
        self._specs[spec.name] = spec
        return self

    @property
    def specs(self) -> dict[str, ToolSpec]:
        return dict(self._specs)

    def declarations(self) -> Optional[list[genai_types.Tool]]:
        """Bentuk deklarasi tool untuk `LiveConnectConfig.tools` (None bila kosong)."""
        if not self._specs:
            return None
        declarations = []
        for spec in self._specs.values():
            behavior = getattr(
                genai_types.Behavior, spec.behavior.upper(), genai_types.Behavior.BLOCKING
            )
            declarations.append(
                genai_types.FunctionDeclaration(
                    name=spec.name,
                    description=spec.description,
                    parameters_json_schema=spec.parameters_json_schema,
                    behavior=behavior,
                )
            )
        return [genai_types.Tool(function_declarations=declarations)]

    async def execute(self, ctx: ToolContext, request: ToolRequest) -> ToolResponse:
        """Jalankan tool; selalu mengembalikan ToolResponse (error tidak dilempar)."""
        spec = self._specs.get(request.name)
        if spec is None:
            return ToolResponse(
                request.id, request.name, {"error": f"Tool '{request.name}' tidak dikenal"}
            )
        try:
            result = await asyncio.wait_for(
                self._invoke(spec, ctx, request.args), timeout=spec.timeout
            )
            return ToolResponse(request.id, request.name, {"output": result})
        except asyncio.TimeoutError:
            return ToolResponse(
                request.id,
                request.name,
                {"error": f"Tool '{request.name}' timeout setelah {spec.timeout}s"},
            )
        except Exception as exc:  # noqa: BLE001 - error tool tidak boleh mematikan sesi
            return ToolResponse(request.id, request.name, {"error": str(exc)})

    async def _invoke(
        self, spec: ToolSpec, ctx: ToolContext, args: dict[str, Any]
    ) -> dict[str, Any]:
        result = spec.handler(ctx, args)
        if inspect.isawaitable(result):
            return await result
        return result
