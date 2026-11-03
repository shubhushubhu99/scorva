"""
Schemas for AI Operations Control Center.
Includes models for Runtime, Model Registry, Task Routing, Fallback, Execution History, and Testing.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from apps.api.modules.evaluations.providers.pi.schemas import (
    PiDiscoveredModel,
    PiModelTestRequest,
    PiModelTestResponse,
    PiRuntimeStatus,
    PiTokenCost,
    PiTokenUsage,
)


# ==============================================================================
# Runtime & Provider Schemas
# ==============================================================================

class ProviderStatusItem(BaseModel):
    name: str  # "pi", "ollama", "mock"
    display_name: str
    is_available: bool
    connection_status: str  # "connected", "offline", "untested", "degraded"
    version: Optional[str] = None
    config_path_or_url: Optional[str] = None
    last_successful_execution_at: Optional[datetime] = None
    last_error: Optional[str] = None
    total_models: int = 0


class AIRuntimeOverviewResponse(BaseModel):
    providers: List[ProviderStatusItem]
    pi_status: PiRuntimeStatus
    global_max_concurrency: int = 10
    default_timeout_seconds: int = 180
    default_provider: str = "openai-codex"
    default_model: str = "gpt-5.6-luna"
    updated_at: datetime


class AIRuntimeSettingsUpdate(BaseModel):
    global_max_concurrency: Optional[int] = Field(None, ge=1, le=50)
    default_timeout_seconds: Optional[int] = Field(None, ge=10, le=600)
    default_provider: Optional[str] = None
    default_model: Optional[str] = None


# ==============================================================================
# Model Registry Schemas
# ==============================================================================

class AIModelItem(BaseModel):
    id: str
    provider: str
    model_id: str
    display_name: str
    context_window: Optional[int] = None
    max_tokens: Optional[int] = None
    input_cost: Optional[float] = None
    output_cost: Optional[float] = None
    capabilities: Optional[Dict[str, Any]] = None
    is_available: bool = True
    is_enabled: bool = True
    is_default: bool = False
    assigned_tasks_count: int = 0
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[str] = None  # "success", "failed", "untested"
    last_test_latency_ms: Optional[int] = None
    last_test_error: Optional[str] = None


class AIModelUpdatePayload(BaseModel):
    is_enabled: Optional[bool] = None
    display_name: Optional[str] = None


class DefaultModelSwitchPayload(BaseModel):
    provider: str
    model_id: str


# ==============================================================================
# Task-Based Model Assignment & Fallback Schemas
# ==============================================================================

class FallbackModelItem(BaseModel):
    provider: str
    model_id: str
    priority: int = 1


class TaskRoutingAssignment(BaseModel):
    task_type: str
    name: str
    description: Optional[str] = None
    is_enabled: bool = True
    primary_provider: str
    primary_model: str
    secondary_provider: Optional[str] = None
    secondary_model: Optional[str] = None
    fallback_models: List[FallbackModelItem] = Field(default_factory=list)
    timeout_seconds: int = 180
    max_retries: int = 2
    parallel_enabled: bool = True
    priority: int = 0


class TaskRoutingUpdatePayload(BaseModel):
    is_enabled: Optional[bool] = None
    primary_provider: Optional[str] = None
    primary_model: Optional[str] = None
    secondary_provider: Optional[str] = None
    secondary_model: Optional[str] = None
    fallback_models: Optional[List[FallbackModelItem]] = None
    timeout_seconds: Optional[int] = Field(None, ge=10, le=600)
    max_retries: Optional[int] = Field(None, ge=0, le=5)
    parallel_enabled: Optional[bool] = None
    priority: Optional[int] = None


# ==============================================================================
# Execution History & Monitoring Schemas
# ==============================================================================

class AIExecutionRecordSummary(BaseModel):
    id: str
    evaluation_id: Optional[str] = None
    submission_id: Optional[str] = None
    task_type: str
    primary_provider: str
    primary_model: str
    actual_provider: str
    actual_model: str
    status: str
    fallback_used: bool
    fallback_reason: Optional[str] = None
    attempt_count: int
    duration_ms: int
    total_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    validation_passed: bool
    error_message: Optional[str] = None
    created_at: datetime


class AIExecutionRecordDetail(AIExecutionRecordSummary):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    prompt_preview: Optional[str] = None
    output_payload: Optional[Dict[str, Any]] = None
    validation_errors: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AIExecutionListResponse(BaseModel):
    total: int
    items: List[AIExecutionRecordSummary]
    page: int
    page_size: int


# ==============================================================================
# Overview Stats Schemas
# ==============================================================================

class AIOperationsControlCenterStats(BaseModel):
    available_models: int = 0
    enabled_models: int = 0
    active_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    fallback_executions: int = 0
    average_execution_time_ms: int = 0
    total_tokens_consumed: Optional[int] = None
    estimated_total_cost: Optional[float] = None
    average_tokens_per_eval: Optional[int] = None
    recent_executions: List[AIExecutionRecordSummary] = Field(default_factory=list)


# ==============================================================================
# Parallel Execution Test Payload
# ==============================================================================

class ParallelTaskExecutionRequest(BaseModel):
    tasks: List[str] = Field(default_factory=lambda: ["code_quality", "security_analysis", "innovation_analysis"])
    test_context: Optional[str] = None


class ParallelTaskExecutionResponse(BaseModel):
    correlation_id: str
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    total_duration_ms: int
    task_results: Dict[str, Any]
    executions: List[AIExecutionRecordSummary]


# ==============================================================================
# Legacy Endpoints (For Backward Compatibility)
# ==============================================================================

class AIEndpointConfig(BaseModel):
    id: str
    name: str
    url: str
    role: str = "primary"
    is_enabled: bool = True
    model_name: Optional[str] = None
    timeout_seconds: int = 120
    is_custom: bool = False


class AIRoutingConfigRequest(BaseModel):
    endpoints: List[AIEndpointConfig]
    primary_endpoint_id: Optional[str] = None
    secondary_endpoint_id: Optional[str] = None


class AIRoutingConfigResponse(BaseModel):
    endpoints: List[AIEndpointConfig]
    primary_endpoint_id: Optional[str] = None
    secondary_endpoint_id: Optional[str] = None
    primary_url: Optional[str] = None
    secondary_url: Optional[str] = None
    primary_enabled: bool = True
    secondary_enabled: bool = True
    primary_model: Optional[str] = None
    secondary_model: Optional[str] = None
    updated_at: datetime


class AIEndpointProbeRequest(BaseModel):
    url: str


class AIEndpointProbeResponse(BaseModel):
    url: str
    is_online: bool
    latency_ms: Optional[float] = None
    version: Optional[str] = None
    available_models: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class AIOperationsStatsResponse(BaseModel):
    total_inspections: int = 0
    primary_used_count: int = 0
    secondary_used_count: int = 0
    fallback_used_count: int = 0
    recent_inspections: List[Dict[str, Any]] = Field(default_factory=list)
