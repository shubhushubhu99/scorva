"""
Exceptions for Pi Runtime and Execution Adapter.
Inherits from Scorva's base AIProviderError to ensure clean error handling and security.
"""

from apps.api.modules.evaluations.ai_provider import AIProviderError


class PiRuntimeError(AIProviderError):
    """Base exception for all Pi runtime errors."""

    def __init__(self, message: str, code: str = "PI_RUNTIME_ERROR", retryable: bool = False):
        super().__init__(message=message, code=code, retryable=retryable)


class PiExecutableNotFoundError(PiRuntimeError):
    """Raised when the Pi executable is not found on the system."""

    def __init__(self, message: str = "Pi CLI executable was not found on the host system."):
        super().__init__(message=message, code="PI_NOT_FOUND", retryable=False)


class PiProcessTimeoutError(PiRuntimeError):
    """Raised when a Pi execution subprocess exceeds the configured timeout."""

    def __init__(self, timeout_seconds: float):
        super().__init__(
            message=f"Pi execution timed out after {timeout_seconds:.1f} seconds.",
            code="PI_TIMEOUT",
            retryable=True,
        )


class PiProcessExecutionError(PiRuntimeError):
    """Raised when the Pi subprocess terminates with a non-zero exit code or stderr error."""

    def __init__(self, message: str, exit_code: int = 1, retryable: bool = True):
        super().__init__(
            message=f"Pi process failed (exit code {exit_code}): {message}",
            code="PI_EXECUTION_FAILED",
            retryable=retryable,
        )
        self.exit_code = exit_code


class PiModelUnavailableError(PiRuntimeError):
    """Raised when the requested model is not supported or not available in Pi."""

    def __init__(self, model_id: str, provider: str, details: str = ""):
        msg = f"Model '{model_id}' (provider '{provider}') is unavailable or not supported in Pi."
        if details:
            msg += f" Details: {details}"
        super().__init__(message=msg, code="PI_MODEL_UNAVAILABLE", retryable=False)


class PiOutputParseError(PiRuntimeError):
    """Raised when Pi's JSON stream or model output cannot be parsed."""

    def __init__(self, message: str = "Failed to parse JSON output from Pi execution."):
        super().__init__(message=message, code="PI_OUTPUT_PARSE_ERROR", retryable=True)


class PiStructuredValidationError(PiRuntimeError):
    """Raised when Pi's output does not conform to the required JSON schema."""

    def __init__(self, message: str):
        super().__init__(
            message=f"Pi model response failed schema validation: {message}",
            code="PI_SCHEMA_VALIDATION_ERROR",
            retryable=True,
        )
