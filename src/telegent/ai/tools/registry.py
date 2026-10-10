"""Registry tool: deklarasi ke Gemini + eksekusi dengan timeout & penanganan error."""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Optional

from google.genai import types as genai_types

from telegent.ai.tools.spec import ToolContext, ToolRequest, ToolResponse, ToolSpec

log = logging.getLogger("telegent.ai.tools")


class ToolRegistry:
    """Menyimpan ToolSpec dan mengeksekusinya dengan aman."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._enabled: dict[str, bool] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    def register(self, spec: ToolSpec) -> "ToolRegistry":
        if spec.name in self._specs:
            raise ValueError(f"Tool '{spec.name}' sudah terdaftar")
        self._specs[spec.name] = spec
        if spec.name not in self._enabled:
            self._enabled[spec.name] = True
        return self

    @property
    def specs(self) -> dict[str, ToolSpec]:
        return dict(self._specs)

    def is_enabled(self, name: str) -> bool:
        if name not in self._specs:
            return False
        return self._enabled.get(name, True)

    def configure(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Ubah status aktif dan/atau parameter satu tool."""
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"Tool '{name}' tidak terdaftar")

        if enabled is False and not spec.can_disable:
            raise ValueError(f"Tool '{name}' tidak dapat dinonaktifkan")

        if enabled is not None:
            self._enabled[name] = enabled

        if config is not None:
            self._configs[name] = config
            # Bangun ulang spec bila tool punya pabrik konfigurasi (mis. zona waktu).
            if spec.config_factory is not None:
                rebuilt = spec.config_factory(config)
                self._specs[name] = rebuilt
                self._enabled.setdefault(name, True)

    def apply_configs(self, configs: dict[str, dict[str, Any]]) -> None:
        """Terapkan konfigurasi tersimpan sekaligus (hidrasi saat runtime dibangun).

        Tool tanpa `config_factory` tetap memakai parameter bawaannya.
        """
        for name, config in configs.items():
            if name not in self._specs:
                log.debug("Konfigurasi tool '%s' diabaikan (tidak terdaftar).", name)
                continue
            try:
                self.configure(name, config=config)
            except (KeyError, ValueError) as exc:
                log.warning("Gagal menerapkan konfigurasi tool '%s': %s", name, exc)

    def declarations(self) -> Optional[list[genai_types.Tool]]:
        """Bentuk deklarasi tool untuk `LiveConnectConfig.tools` (None bila kosong)."""
        active_specs = [
            spec for spec in self._specs.values() if self.is_enabled(spec.name)
        ]
        if not active_specs:
            return None
        declarations = []
        for spec in active_specs:
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
        if not self.is_enabled(request.name):
            return ToolResponse(
                request.id,
                request.name,
                {"error": f"Tool '{request.name}' sedang dinonaktifkan"},
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
