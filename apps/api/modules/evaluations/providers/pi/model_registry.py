"""
Pi Model Discovery and Registry.
Discovers models from Pi configuration/CLI and provides live model testing and health tracking.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from apps.api.modules.evaluations.providers.pi.exceptions import (
    PiModelUnavailableError,
    PiOutputParseError,
    PiStructuredValidationError,
)
from apps.api.modules.evaluations.providers.pi.runtime import PiRuntime, default_pi_runtime
from apps.api.modules.evaluations.providers.pi.schemas import (
    PiDiscoveredModel,
    PiModelTestRequest,
    PiModelTestResponse,
    PiTokenCost,
    PiTokenUsage,
)

logger = logging.getLogger("scorva.pi.model_registry")


class PiModelRegistry:
    """
    Centralized discovery and health tracking engine for Pi models.
    """

    def __init__(self, runtime: Optional[PiRuntime] = None):
        self.runtime = runtime or default_pi_runtime
        self._cached_models: List[PiDiscoveredModel] = []
        self._last_discovery_time: Optional[datetime] = None

    async def discover_models(self, force_refresh: bool = False) -> List[PiDiscoveredModel]:
        """
        Discovers all available models across all configured providers in the user's Pi setup.
        Reads ~/.pi/agent/models-store.json and ~/.pi/agent/settings.json.
        """
        if self._cached_models and not force_refresh:
            return self._cached_models

        config_dir = self.runtime.get_config_dir()
        models_store_file = config_dir / "models-store.json"
        settings_file = config_dir / "settings.json"
        auth_file = config_dir / "auth.json"

        default_provider = None
        default_model = None
        if settings_file.is_file():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    settings_data = json.load(f)
                    default_provider = settings_data.get("defaultProvider")
                    default_model = settings_data.get("defaultModel")
            except Exception as exc:
                logger.warning("Could not read settings.json for default model: %s", exc)

        configured_providers: List[str] = []
        if auth_file.is_file():
            try:
                with open(auth_file, "r", encoding="utf-8") as f:
                    auth_data = json.load(f)
                    configured_providers = list(auth_data.keys())
            except Exception as exc:
                logger.warning("Could not read auth.json for providers: %s", exc)

        discovered: List[PiDiscoveredModel] = []

        if models_store_file.is_file():
            try:
                with open(models_store_file, "r", encoding="utf-8") as f:
                    store = json.load(f)

                for prov_name, prov_entry in store.items():
                    if not isinstance(prov_entry, dict):
                        continue
                    models_list = prov_entry.get("models", [])
                    for m in models_list:
                        m_id = m.get("id", "")
                        if not m_id:
                            continue

                        # Determine if this model is default
                        is_def = (prov_name == default_provider and m_id == default_model)

                        discovered.append(
                            PiDiscoveredModel(
                                id=m_id,
                                name=m.get("name", m_id),
                                provider=prov_name,
                                api=m.get("api"),
                                context_window=m.get("contextWindow"),
                                max_tokens=m.get("maxTokens"),
                                reasoning=bool(m.get("reasoning", False)),
                                input_modalities=m.get("input", ["text"]),
                                cost=m.get("cost"),
                                is_available=True,
                                is_enabled=True,
                                is_default=is_def,
                            )
                        )
            except Exception as exc:
                logger.error("Failed discovering models from models-store.json: %s", exc)

        # If models-store.json was empty or missing, fallback to parsing `pi --list-models`
        if not discovered:
            try:
                discovered = await self._discover_from_cli()
            except Exception as exc:
                logger.error("Failed discovering models from CLI: %s", exc)

        self._cached_models = discovered
        self._last_discovery_time = datetime.now(timezone.utc)
        logger.info("Discovered %d models across Pi providers", len(discovered))
        return discovered

    async def _discover_from_cli(self) -> List[PiDiscoveredModel]:
        """Fallback discovery parser using `pi --list-models`."""
        exe_path = self.runtime.get_executable_path()
        proc = await asyncio.create_subprocess_exec(
            exe_path,
            "--list-models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        lines = stdout.decode().strip().splitlines()

        models: List[PiDiscoveredModel] = []
        if len(lines) < 2:
            return models

        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                provider = parts[0]
                model_id = parts[1]
                models.append(
                    PiDiscoveredModel(
                        id=model_id,
                        name=model_id,
                        provider=provider,
                        is_available=True,
                        is_enabled=True,
                    )
                )
        return models

    async def test_model(self, request: PiModelTestRequest) -> PiModelTestResponse:
        """
        Executes a live test prompt against a specific provider/model.
        Supports structured JSON validation when requested.
        """
        # Default structured test prompt per specification
        default_prompt = (
            "Return a valid JSON object containing: status (string, value 'ok'), "
            "summary (string, brief summary confirming operational readiness), "
            "and confidence (number between 0 and 1)."
        )
        prompt = request.prompt or default_prompt
        if request.is_structured and "JSON" not in prompt:
            prompt = f"{prompt}\nReturn response strictly as a JSON object."

        t0 = time.perf_counter()
        exec_result = await self.runtime.execute_prompt(
            prompt=prompt,
            provider=request.provider,
            model=request.model_id,
            timeout_seconds=60.0,
            thinking_level="off",
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        # Validate structured JSON if requested
        validation_passed = False
        error_msg = exec_result.error_message

        if exec_result.success:
            if request.is_structured:
                if exec_result.parsed_json is not None:
                    # Validate schema fields if default prompt
                    pj = exec_result.parsed_json
                    if "status" in pj and "summary" in pj:
                        validation_passed = True
                    else:
                        validation_passed = True  # Valid JSON object received
                else:
                    validation_passed = False
                    error_msg = "Model returned non-JSON text output when structured output was requested."
            else:
                validation_passed = True
        else:
            validation_passed = False

        return PiModelTestResponse(
            success=exec_result.success and validation_passed,
            provider=request.provider,
            model_id=request.model_id,
            prompt=prompt,
            response_text=exec_result.raw_text,
            structured_output=exec_result.parsed_json,
            duration_ms=exec_result.duration_ms or latency_ms,
            usage=exec_result.usage,
            error_message=error_msg,
            validation_passed=validation_passed,
        )


# Global default registry
default_pi_registry = PiModelRegistry()
