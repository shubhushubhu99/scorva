"""
Pi Runtime Subprocess Manager.
Handles executable discovery, environment verification, asynchronous execution,
concurrency bounding, timeout enforcement, and clean termination.
"""

import asyncio
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

from apps.api.modules.evaluations.providers.pi.exceptions import (
    PiExecutableNotFoundError,
    PiModelUnavailableError,
    PiOutputParseError,
    PiProcessExecutionError,
    PiProcessTimeoutError,
    PiRuntimeError,
)
from apps.api.modules.evaluations.providers.pi.schemas import (
    PiExecutionResult,
    PiRuntimeStatus,
    PiTokenCost,
    PiTokenUsage,
)

logger = logging.getLogger("scorva.pi.runtime")

DEFAULT_MAX_CONCURRENT_SESSIONS = 5
DEFAULT_TIMEOUT_SECONDS = 180.0


class PiRuntime:
    """
    Manages the global Pi CLI execution environment and runs isolated evaluation sessions.
    """

    def __init__(
        self,
        executable_path: Optional[str] = None,
        config_dir: Optional[str] = None,
        max_concurrent_sessions: int = DEFAULT_MAX_CONCURRENT_SESSIONS,
        default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._custom_executable_path = executable_path
        self._custom_config_dir = config_dir
        self.semaphore = asyncio.Semaphore(max_concurrent_sessions)
        self.default_timeout_seconds = default_timeout_seconds

    def get_executable_path(self) -> str:
        """
        Locates the Pi executable across environment variables and standard binary paths.
        """
        # 1. Custom or environment override
        env_path = os.environ.get("PI_EXECUTABLE_PATH") or self._custom_executable_path
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path

        # 2. System PATH lookup
        which_path = shutil.which("pi")
        if which_path:
            return which_path

        # 3. Known candidate locations
        home = str(Path.home())
        candidates = [
            f"{home}/.local/bin/pi",
            f"{home}/.pi/agent/bin/pi",
            "/usr/local/bin/pi",
            "/usr/bin/pi",
        ]
        for candidate in candidates:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        raise PiExecutableNotFoundError(
            "Pi CLI executable was not found. Please verify that Pi is installed globally "
            "or set PI_EXECUTABLE_PATH."
        )

    def is_available(self) -> bool:
        """Checks if the Pi executable exists and is accessible."""
        try:
            self.get_executable_path()
            return True
        except Exception:
            return False

    def get_config_dir(self) -> Path:
        """
        Returns the resolved Pi configuration directory (~/.pi/agent by default).
        """
        if self._custom_config_dir:
            return Path(self._custom_config_dir).expanduser()

        env_dir = os.environ.get("PI_CODING_AGENT_DIR")
        if env_dir:
            return Path(env_dir).expanduser()

        return Path.home() / ".pi" / "agent"

    async def get_runtime_status(self) -> PiRuntimeStatus:
        """
        Probes the Pi installation, CLI version, configuration directory,
        and available providers. Never exposes credentials.
        """
        config_dir = self.get_config_dir()
        models_store = config_dir / "models-store.json"
        auth_store = config_dir / "auth.json"
        settings_file = config_dir / "settings.json"

        exe_path: Optional[str] = None
        version: Optional[str] = None
        is_installed = False

        try:
            exe_path = self.get_executable_path()
            # Probe version
            proc = await asyncio.create_subprocess_exec(
                exe_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                is_installed = True
                version = stdout.decode().strip()
        except Exception as exc:
            logger.debug("Failed probing Pi executable: %s", exc)

        default_provider = None
        default_model = None
        if settings_file.is_file():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_provider = data.get("defaultProvider")
                    default_model = data.get("defaultModel")
            except Exception as exc:
                logger.warning("Failed reading Pi settings.json: %s", exc)

        configured_providers: List[str] = []
        if auth_store.is_file():
            try:
                with open(auth_store, "r", encoding="utf-8") as f:
                    auth_data = json.load(f)
                    configured_providers = list(auth_data.keys())
            except Exception as exc:
                logger.warning("Failed reading Pi auth.json provider names: %s", exc)

        total_models = 0
        if models_store.is_file():
            try:
                with open(models_store, "r", encoding="utf-8") as f:
                    store_data = json.load(f)
                    for _, prov_data in store_data.items():
                        if isinstance(prov_data, dict) and "models" in prov_data:
                            total_models += len(prov_data["models"])
            except Exception:
                pass

        return PiRuntimeStatus(
            is_installed=is_installed,
            executable_path=exe_path,
            version=version,
            config_dir=str(config_dir),
            models_store_exists=models_store.is_file(),
            auth_store_exists=auth_store.is_file(),
            default_provider=default_provider,
            default_model=default_model,
            configured_providers=configured_providers,
            total_discovered_models=total_models,
        )

    async def execute_prompt(
        self,
        prompt: str,
        provider: str,
        model: str,
        timeout_seconds: Optional[float] = None,
        thinking_level: Optional[str] = "off",
        system_prompt: Optional[str] = None,
    ) -> PiExecutionResult:
        """
        Executes an isolated, non-interactive Pi session and parses the structured JSONL events.
        Enforces timeout, concurrency limit, and process cleanup.
        """
        exe_path = self.get_executable_path()
        timeout = timeout_seconds or self.default_timeout_seconds

        # Build command args with strict session isolation
        cmd: List[str] = [
            exe_path,
            "--provider", provider,
            "--model", model,
            "--mode", "json",
            "-p",  # print / non-interactive
            "--no-session",  # ephemeral session, no history persistence
            "--no-tools",  # disable tools
            "--no-skills",
            "--no-prompt-templates",
            "--no-extensions",
            "--no-context-files",
        ]

        if thinking_level:
            cmd.extend(["--thinking", thinking_level])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        cmd.extend(["--", prompt])

        # Execute under semaphore to bound concurrency
        async with self.semaphore:
            logger.info("Executing Pi model: %s/%s (timeout=%ss)", provider, model, timeout)
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError as exc:
                if proc:
                    try:
                        proc.terminate()
                        await asyncio.wait_for(proc.wait(), timeout=3.0)
                    except (asyncio.TimeoutError, ProcessLookupError):
                        try:
                            proc.kill()
                            await proc.wait()
                        except ProcessLookupError:
                            pass
                logger.error("Pi execution timed out for %s/%s after %ss", provider, model, timeout)
                raise PiProcessTimeoutError(timeout) from exc
            except Exception as exc:
                if proc:
                    try:
                        proc.kill()
                        await proc.wait()
                    except ProcessLookupError:
                        pass
                raise PiProcessExecutionError(str(exc)) from exc

            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            return self._parse_jsonl_output(
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                exit_code=proc.returncode,
                provider=provider,
                model=model,
            )

    def _parse_jsonl_output(
        self,
        stdout_text: str,
        stderr_text: str,
        exit_code: int,
        provider: str,
        model: str,
    ) -> PiExecutionResult:
        """
        Parses JSONL output events generated by Pi in `--mode json`.
        Extracts assistant text, usage, duration, and error messages.
        """
        lines = stdout_text.strip().splitlines()
        assistant_text_chunks: List[str] = []
        duration_ms = 0
        usage: Optional[PiTokenUsage] = None
        stop_reason: Optional[str] = None
        error_message: Optional[str] = None
        success = False

        # First check if agent_end is present with final assistant message
        agent_end_msg = None
        for line in reversed(lines):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                event = json.loads(line_str)
            except Exception:
                continue
            if event.get("type") == "agent_end":
                messages = event.get("messages", [])
                for msg in reversed(messages):
                    if msg.get("role") == "assistant":
                        agent_end_msg = msg
                        break
                if agent_end_msg:
                    break

        if agent_end_msg:
            msg = agent_end_msg
            for item in msg.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    assistant_text_chunks.append(item.get("text", ""))
            if msg.get("durationMs"):
                duration_ms = int(msg.get("durationMs"))
            if msg.get("stopReason"):
                stop_reason = msg.get("stopReason")
            if msg.get("errorMessage"):
                error_message = msg.get("errorMessage")
            u = msg.get("usage")
            if isinstance(u, dict):
                cost_dict = u.get("cost")
                token_cost = None
                if isinstance(cost_dict, dict):
                    token_cost = PiTokenCost(
                        input=float(cost_dict.get("input", 0.0)),
                        output=float(cost_dict.get("output", 0.0)),
                        cache_read=float(cost_dict.get("cacheRead", 0.0)),
                        cache_write=float(cost_dict.get("cacheWrite", 0.0)),
                        total=float(cost_dict.get("total", 0.0)),
                    )
                usage = PiTokenUsage(
                    input=int(u.get("input", 0)),
                    output=int(u.get("output", 0)),
                    cache_read=int(u.get("cacheRead", 0)),
                    cache_write=int(u.get("cacheWrite", 0)),
                    reasoning=int(u.get("reasoning", 0)),
                    total_tokens=int(u.get("totalTokens", 0)),
                    cost=token_cost,
                )
        else:
            # Fallback to message_end
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    event = json.loads(line_str)
                except Exception:
                    continue

                if event.get("type") == "message_end":
                    msg = event.get("message", {})
                    if msg.get("role") == "assistant":
                        for item in msg.get("content", []):
                            if isinstance(item, dict) and item.get("type") == "text":
                                assistant_text_chunks.append(item.get("text", ""))
                        if msg.get("durationMs"):
                            duration_ms = int(msg.get("durationMs"))
                        if msg.get("stopReason"):
                            stop_reason = msg.get("stopReason")
                        if msg.get("errorMessage"):
                            error_message = msg.get("errorMessage")
                        u = msg.get("usage")
                        if isinstance(u, dict):
                            cost_dict = u.get("cost")
                            token_cost = None
                            if isinstance(cost_dict, dict):
                                token_cost = PiTokenCost(
                                    input=float(cost_dict.get("input", 0.0)),
                                    output=float(cost_dict.get("output", 0.0)),
                                    cache_read=float(cost_dict.get("cacheRead", 0.0)),
                                    cache_write=float(cost_dict.get("cacheWrite", 0.0)),
                                    total=float(cost_dict.get("total", 0.0)),
                                )
                            usage = PiTokenUsage(
                                input=int(u.get("input", 0)),
                                output=int(u.get("output", 0)),
                                cache_read=int(u.get("cacheRead", 0)),
                                cache_write=int(u.get("cacheWrite", 0)),
                                reasoning=int(u.get("reasoning", 0)),
                                total_tokens=int(u.get("totalTokens", 0)),
                                cost=token_cost,
                            )

        raw_text = "".join(assistant_text_chunks).strip()

        # Handle errors
        if stop_reason == "error" or error_message:
            return PiExecutionResult(
                success=False,
                provider=provider,
                model=model,
                raw_text=raw_text,
                duration_ms=duration_ms,
                stop_reason=stop_reason,
                error_message=error_message or "Unknown model inference error",
                usage=usage,
            )

        if exit_code != 0:
            err = stderr_text.strip() or f"Process exited with code {exit_code}"
            return PiExecutionResult(
                success=False,
                provider=provider,
                model=model,
                raw_text=raw_text,
                duration_ms=duration_ms,
                stop_reason="process_error",
                error_message=err,
                usage=usage,
            )

        # Attempt to parse as JSON if it looks like a JSON response
        parsed_json = None
        if raw_text:
            cleaned = raw_text.strip()
            try:
                parsed_json = json.loads(cleaned, strict=False)
            except Exception as e1:
                logger.debug("Direct JSON decode failed: %s", e1)
                parsed_json = None

            if not isinstance(parsed_json, dict):
                fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_text, re.DOTALL)
                if fence_match:
                    try:
                        parsed_json = json.loads(fence_match.group(1).strip(), strict=False)
                    except Exception as e2:
                        logger.debug("Code fence JSON decode failed: %s", e2)
                        parsed_json = None

            if not isinstance(parsed_json, dict):
                first_brace = raw_text.find("{")
                last_brace = raw_text.rfind("}")
                if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                    candidate = raw_text[first_brace : last_brace + 1].strip()
                    try:
                        parsed_json = json.loads(candidate, strict=False)
                    except Exception as e3:
                        logger.debug("Outermost brace JSON decode failed: %s", e3)
                        parsed_json = None

            if not isinstance(parsed_json, dict):
                parsed_json = None

        return PiExecutionResult(
            success=True,
            provider=provider,
            model=model,
            raw_text=raw_text,
            parsed_json=parsed_json,
            usage=usage,
            duration_ms=duration_ms,
            stop_reason=stop_reason or "stop",
        )


# Global default runtime instance
default_pi_runtime = PiRuntime()
