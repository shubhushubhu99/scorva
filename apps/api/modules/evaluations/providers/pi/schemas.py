"""
Pydantic Schemas for Pi Runtime Integration and Model Operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PiTokenCost(BaseModel):
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    total: float = 0.0


class PiTokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int = 0
    total_tokens: int = 0
    cost: Optional[PiTokenCost] = None


class PiDiscoveredModel(BaseModel):
    id: str
    name: str
    provider: str
    api: Optional[str] = None
    context_window: Optional[int] = None
    max_tokens: Optional[int] = None
    reasoning: bool = False
    input_modalities: List[str] = Field(default_factory=list)
    cost: Optional[Dict[str, Any]] = None
    is_available: bool = True
    is_enabled: bool = True
    is_default: bool = False
    assigned_tasks_count: int = 0
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_latency_ms: Optional[int] = None
    last_test_error: Optional[str] = None


class PiRuntimeStatus(BaseModel):
    is_installed: bool
    executable_path: Optional[str] = None
    version: Optional[str] = None
    config_dir: str
    models_store_exists: bool
    auth_store_exists: bool
    default_provider: Optional[str] = None
    default_model: Optional[str] = None
    configured_providers: List[str] = Field(default_factory=list)
    total_discovered_models: int = 0


class PiExecutionResult(BaseModel):
    success: bool
    provider: str
    model: str
    raw_text: str = ""
    parsed_json: Optional[Dict[str, Any]] = None
    usage: Optional[PiTokenUsage] = None
    duration_ms: int = 0
    stop_reason: Optional[str] = None
    error_message: Optional[str] = None


class PiModelTestRequest(BaseModel):
    provider: str
    model_id: str
    prompt: Optional[str] = None
    is_structured: bool = True
    schema_definition: Optional[Dict[str, Any]] = None


class PiModelTestResponse(BaseModel):
    success: bool
    provider: str
    model_id: str
    prompt: str
    response_text: str
    structured_output: Optional[Dict[str, Any]] = None
    duration_ms: int
    usage: Optional[PiTokenUsage] = None
    error_message: Optional[str] = None
    validation_passed: bool
