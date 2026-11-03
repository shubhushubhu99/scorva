"""
Pi AI Provider Client Adapter.
Implements Scorva's AIProviderClient protocol for vendor-neutral evaluation orchestration.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from apps.api.modules.evaluations.ai_provider import (
    AIProviderClient,
    AIProviderConnectionError,
    AIProviderError,
    AIProviderFormatError,
    AIProviderTimeoutError,
)
from apps.api.modules.evaluations.providers.pi.exceptions import (
    PiExecutableNotFoundError,
    PiModelUnavailableError,
    PiProcessTimeoutError,
    PiRuntimeError,
)
from apps.api.modules.evaluations.providers.pi.model_registry import (
    PiModelRegistry,
    default_pi_registry,
)
from apps.api.modules.evaluations.providers.pi.runtime import PiRuntime, default_pi_runtime
from apps.api.modules.evaluations.providers.pi.schemas import PiExecutionResult, PiTokenUsage
from apps.api.modules.evaluations.providers.pi.session_manager import (
    PiSessionManager,
    default_session_manager,
)

logger = logging.getLogger("scorva.pi.client")


class PiProviderClient:
    """
    Adapter implementing the AIProviderClient Protocol backed by the local Pi runtime.
    Guarantees session isolation, structured validation, and token accounting.
    """

    def __init__(
        self,
        default_provider: Optional[str] = None,
        default_model: Optional[str] = None,
        session_manager: Optional[PiSessionManager] = None,
        registry: Optional[PiModelRegistry] = None,
    ):
        self.session_manager = session_manager or default_session_manager
        self.registry = registry or default_pi_registry
        self.default_provider = default_provider or "openai-codex"
        self.default_model = default_model or "gpt-5.6-luna"

    def _resolve_provider_and_model(self, model_name: str) -> Tuple[str, str]:
        """
        Resolves provider and model_id from a model specifier.
        Supports 'provider/model_id' and bare 'model_id'.
        """
        if "/" in model_name:
            parts = model_name.split("/", 1)
            return parts[0].strip(), parts[1].strip()

        # Bare model name: check if configured default model matches, else use default provider
        return self.default_provider, model_name.strip()

    async def generate_evaluation(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model_name: str,
        timeout_seconds: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """
        Implements AIProviderClient protocol.
        Submits prompt to Pi with schema constraints and returns parsed JSON output.
        """
        detailed = await self.generate_evaluation_detailed(
            prompt=prompt,
            schema=schema,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return detailed["output"]

    async def generate_evaluation_detailed(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model_name: str,
        timeout_seconds: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes evaluation and returns parsed output together with execution metrics:
        duration_ms, usage, provider, model.
        """
        provider, model_id = self._resolve_provider_and_model(model_name)

        # Append schema requirements to prompt
        schema_str = json.dumps(schema, indent=2)
        system_instruction = (
            "You are Scorva's neutral AI evaluation engine. "
            "You MUST output valid, well-formed JSON conforming exactly to the following schema:\n"
            f"{schema_str}\n"
            "Do NOT include any commentary, explanations, or markdown fences outside the JSON object."
        )

        full_prompt = f"{prompt}\n\nStrict output requirement: Respond ONLY with a valid JSON object matching the requested schema."

        try:
            exec_result: PiExecutionResult = await self.session_manager.execute_isolated_evaluation(
                prompt=full_prompt,
                provider=provider,
                model=model_id,
                correlation_id=correlation_id,
                timeout_seconds=timeout_seconds,
                thinking_level="off",
                system_prompt=system_instruction,
            )
        except PiProcessTimeoutError as exc:
            raise AIProviderTimeoutError(str(exc)) from exc
        except PiExecutableNotFoundError as exc:
            raise AIProviderConnectionError(str(exc)) from exc
        except Exception as exc:
            raise AIProviderError(f"Pi execution failed: {exc}") from exc

        if not exec_result.success:
            err_msg = exec_result.error_message or "Model returned an error"
            if "not found" in err_msg.lower() or "not supported" in err_msg.lower():
                raise PiModelUnavailableError(model_id, provider, err_msg)
            raise AIProviderError(
                f"Pi inference error ({provider}/{model_id}): {err_msg}",
                code="PI_INFERENCE_ERROR",
                retryable=True,
            )

        if exec_result.parsed_json is None:
            raise AIProviderFormatError(
                f"Pi model ({provider}/{model_id}) returned non-JSON output: {exec_result.raw_text[:200]}"
            )

        return {
            "output": exec_result.parsed_json,
            "provider": provider,
            "model": model_id,
            "duration_ms": exec_result.duration_ms,
            "usage": exec_result.usage.model_dump() if exec_result.usage else None,
            "raw_text": exec_result.raw_text,
        }
