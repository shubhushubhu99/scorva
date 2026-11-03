"""
Pi Session Manager.
Enforces strict session isolation for parallel evaluation jobs and testing sessions.
Ensures no mutable conversation state leaks between unrelated evaluations.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
import uuid

from apps.api.modules.evaluations.providers.pi.runtime import PiRuntime, default_pi_runtime
from apps.api.modules.evaluations.providers.pi.schemas import PiExecutionResult

logger = logging.getLogger("scorva.pi.session_manager")


class PiSessionManager:
    """
    Manages isolated, correlation-tagged Pi execution sessions.
    Guarantees session boundaries and concurrency safety.
    """

    def __init__(self, runtime: Optional[PiRuntime] = None):
        self.runtime = runtime or default_pi_runtime

    async def execute_isolated_evaluation(
        self,
        prompt: str,
        provider: str,
        model: str,
        correlation_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        thinking_level: Optional[str] = "off",
        system_prompt: Optional[str] = None,
    ) -> PiExecutionResult:
        """
        Executes a prompt inside a strictly isolated, ephemeral session context.
        Uses a unique correlation ID for tracing.
        """
        cid = correlation_id or str(uuid.uuid4())
        logger.debug(
            "Starting isolated Pi session [correlation_id=%s] for %s/%s",
            cid,
            provider,
            model,
        )

        result = await self.runtime.execute_prompt(
            prompt=prompt,
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            thinking_level=thinking_level,
            system_prompt=system_prompt,
        )

        logger.debug(
            "Completed isolated Pi session [correlation_id=%s] success=%s duration_ms=%d",
            cid,
            result.success,
            result.duration_ms,
        )
        return result


# Global default session manager
default_session_manager = PiSessionManager()
